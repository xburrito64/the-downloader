"""The local API the UI talks to.

It only translates between HTTP and the engine: no download logic lives here.
The server listens on 127.0.0.1 only, and every request must carry the session
token, so other programs and web pages on this PC cannot use it.

Built on Starlette directly. FastAPI was measured at 13 MB more memory and
half a second more startup for the same handful of routes.
"""

import asyncio
import hmac
import json
import os
import re
import subprocess
import threading
import webbrowser
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import asdict, fields, replace
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import APP_NAME, config, covers, spotify_auth, startup, updater
from .providers.base import ProviderError, Resolved
from .providers.youtube import LOGIN_SOURCES, test_login
from .queue import DownloadQueue
from .store import ACTIVE, Store

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_MODES = {"audio", "video"}
_AUDIO_FORMATS = {"original", "mp3"}
_VIDEO_QUALITIES = {"best", "1080p", "720p"}
_MAX_REMEMBERED_LINKS = 20  # previews kept in memory so the UI can queue them by number
_HEARTBEAT_SECONDS = 20
_MAX_BODY_BYTES = 1_000_000
_SETTING_TYPES = {f.name: f.type for f in fields(config.Settings)}


_VERSION: dict | None = None


def _version() -> dict:
    """The installed version, read once: it cannot change while the app runs."""
    global _VERSION
    if _VERSION is None:
        try:
            _VERSION = updater.version()
        except updater.UpdateError:
            _VERSION = {"commit": "", "date": "", "git": False}
    return _VERSION


class ApiError(Exception):
    """Ends a request with a status code and a message written for the user."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class EventHub:
    """Passes engine events from the worker threads to every connected UI."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set[asyncio.Queue] = set()
        self._closed = False

    def attach(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event: dict) -> None:
        """Called from any thread."""
        if self._loop is not None and self._clients:
            self._loop.call_soon_threadsafe(self._deliver, event)

    def _deliver(self, event: dict) -> None:
        for client in self._clients:
            if client.full():
                # A UI that cannot keep up loses progress ticks, never status changes.
                if event.get("type") == "progress":
                    continue
                try:
                    client.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            client.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        client: asyncio.Queue = asyncio.Queue(maxsize=500)
        if self._closed:
            client.put_nowait(None)
        else:
            self._clients.add(client)
        return client

    def unsubscribe(self, client: asyncio.Queue) -> None:
        self._clients.discard(client)

    def close(self) -> None:
        """End every event stream. Called from any thread when the app shuts down.

        An open stream would otherwise keep the server waiting and stop it from
        shutting down cleanly.
        """
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._close)

    def _close(self) -> None:
        self._closed = True
        for client in self._clients:
            while not client.empty():
                client.get_nowait()
            client.put_nowait(None)  # None tells the stream to end
        self._clients.clear()


class AppState:
    """Everything the endpoints share."""

    def __init__(self, settings: config.Settings, store: Store, providers: list, token: str,
                 settings_file: Path | None = None, ffmpeg_path: str | None = None,
                 ui_dir: Path | None = None) -> None:
        self.settings = settings
        self.settings_file = settings_file
        self.ffmpeg_path = ffmpeg_path  # used to shrink cover pictures
        self.ui_dir = ui_dir  # the built UI files; None when only the API is wanted
        self.store = store
        self.providers = providers
        self.token = token
        self.hub = EventHub()
        self.queue = DownloadQueue(store, {p.name: p for p in providers}, settings, self.hub.publish)
        self._resolved: OrderedDict[int, tuple[str, Resolved]] = OrderedDict()
        self._next_resolve_id = 1
        self._lock = threading.Lock()
        self.spotify_login_state = "idle"  # "idle", "waiting", "done" or an error message

    def remember(self, provider_name: str, resolved: Resolved) -> int:
        with self._lock:
            resolve_id = self._next_resolve_id
            self._next_resolve_id += 1
            self._resolved[resolve_id] = (provider_name, resolved)
            while len(self._resolved) > _MAX_REMEMBERED_LINKS:
                self._resolved.popitem(last=False)
            return resolve_id

    def recall(self, resolve_id: int) -> tuple[str, Resolved]:
        with self._lock:
            found = self._resolved.get(resolve_id)
        if found is None:
            raise ApiError(404, "This preview is no longer available. Paste the link again.")
        return found

    def provider(self, name: str):
        return next(p for p in self.providers if p.name == name)


# ---- reading values out of a request --------------------------------------

def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _choice(body: dict, key: str, allowed: set[str], default: str) -> str:
    value = body.get(key, default)
    if value not in allowed:
        raise ApiError(422, f"{key} must be one of: {', '.join(sorted(allowed))}.")
    return value


def _query_int(request: Request, key: str, default: int, low: int, high: int) -> int:
    raw = request.query_params.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(422, f"{key} must be a whole number.") from None
    if not low <= value <= high:
        raise ApiError(422, f"{key} must be between {low} and {high}.")
    return value


def _apply_settings(settings: config.Settings, body: dict) -> None:
    changes = {}
    for key, value in body.items():
        expected = _SETTING_TYPES.get(key)
        if expected is None or value is None:
            continue  # unknown keys are ignored, like in the settings file
        if isinstance(value, bool) != (expected is bool) or not isinstance(value, expected):
            raise ApiError(422, f"{key} has the wrong kind of value.")
        changes[key] = value.strip() if isinstance(value, str) else value

    for key in ("youtube_subdir", "spotify_subdir", "youtube_template", "spotify_template"):
        if key in changes and not changes[key]:
            raise ApiError(422, f"{key} must not be empty.")
    if "output_dir" in changes and not Path(changes["output_dir"]).is_absolute():
        raise ApiError(422, "The output folder must be a full path, for example C:\\Music.")
    for key in ("youtube_subdir", "spotify_subdir"):
        if key in changes and (Path(changes[key]).is_absolute() or ".." in Path(changes[key]).parts):
            raise ApiError(422, f"{key} must be a folder name inside the output folder.")
    if "mode" in changes and changes["mode"] not in _MODES:
        raise ApiError(422, "mode must be audio or video.")
    if "audio_format" in changes and changes["audio_format"] not in _AUDIO_FORMATS:
        raise ApiError(422, "audio_format must be original or mp3.")
    if "video_quality" in changes and changes["video_quality"] not in _VIDEO_QUALITIES:
        raise ApiError(422, "video_quality must be best, 1080p or 720p.")
    if "max_parallel_downloads" in changes and not 1 <= changes["max_parallel_downloads"] <= 8:
        raise ApiError(422, "max_parallel_downloads must be between 1 and 8.")
    for key in ("ffmpeg_path", "deno_path"):
        if changes.get(key) and not Path(changes[key]).is_file():
            raise ApiError(422, f"{key}: no such file.")
    if "youtube_login" in changes and changes["youtube_login"] not in ("", "file", *LOGIN_SOURCES):
        raise ApiError(422, "youtube_login is not a known choice.")
    if changes.get("youtube_cookies_file") and not Path(changes["youtube_cookies_file"]).is_file():
        raise ApiError(422, "The cookies file could not be found.")
    # Nothing is changed until everything has passed.
    for key, value in changes.items():
        setattr(settings, key, value)


def create_app(state: AppState) -> Starlette:
    def check_access(request: Request) -> None:
        # The Host check stops a web page from reaching this server through a made-up domain name.
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            raise ApiError(403, "Forbidden")
        given = request.headers.get("x-token") or request.query_params.get("token") or ""
        if not hmac.compare_digest(given.encode(), state.token.encode()):
            raise ApiError(401, "Missing or wrong token")

    def route(path: str, method: str, handler, with_body: bool = False) -> Route:
        """Wrap a plain function as a guarded route.

        The handler runs in a worker thread, so slow work (reading a link,
        searching for matches) never blocks other requests or the event stream.
        """
        async def endpoint(request: Request):
            try:
                check_access(request)
                body: dict = {}
                if with_body:
                    raw = await request.body()
                    if len(raw) > _MAX_BODY_BYTES:
                        raise ApiError(413, "The request is too large.")
                    try:
                        body = json.loads(raw or b"{}")
                    except ValueError:
                        raise ApiError(422, "The request is not valid JSON.") from None
                    if not isinstance(body, dict):
                        raise ApiError(422, "The request must be a JSON object.")
                result = await run_in_threadpool(handler, request, body)
            except ApiError as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status)
            except ProviderError as exc:
                return JSONResponse({"detail": str(exc)}, status_code=422)
            return JSONResponse(result)

        return Route(path, endpoint, methods=[method])

    # ---- status and settings ---------------------------------------------

    def status(_request: Request, _body: dict):
        checks = startup.run_checks(state.settings)
        return {
            "app": APP_NAME,
            "checks": [asdict(check) for check in checks],
            "ready": all(check.ok for check in checks if check.required),
            "spotify_logged_in": spotify_auth.is_logged_in(),
            "spotify_login_state": state.spotify_login_state,
            "spotify_redirect_uri": spotify_auth.REDIRECT_URI,
            "version": _version(),
            "library_note": state.store.health,
        }

    def get_settings(_request: Request, _body: dict):
        return asdict(state.settings)

    def put_settings(_request: Request, body: dict):
        _apply_settings(state.settings, body)
        config.save(state.settings, state.settings_file)
        state.queue.set_parallel(state.settings.max_parallel_downloads)  # takes effect at once
        return asdict(state.settings)

    # ---- Spotify login ---------------------------------------------------

    def spotify_login(_request: Request, _body: dict):
        if not state.settings.spotify_client_id:
            raise ApiError(422, "Add your Spotify client ID in Settings first.")
        if state.spotify_login_state == "waiting":
            return {"state": "waiting"}
        state.spotify_login_state = "waiting"

        def run() -> None:
            try:
                spotify_auth.login(state.settings.spotify_client_id)
                state.spotify_login_state = "done"
            except spotify_auth.SpotifyAuthError as exc:
                state.spotify_login_state = str(exc)
            state.hub.publish({"type": "spotify", "state": state.spotify_login_state,
                               "logged_in": spotify_auth.is_logged_in()})

        threading.Thread(target=run, name="spotify-login", daemon=True).start()
        return {"state": "waiting"}

    def spotify_logout(_request: Request, _body: dict):
        spotify_auth.logout()
        state.spotify_login_state = "idle"
        return {"logged_in": False}

    # ---- reading links ---------------------------------------------------

    def resolve(_request: Request, body: dict):
        link = body.get("link")
        if not isinstance(link, str) or not link.strip() or len(link) > 2000:
            raise ApiError(422, "Paste a link first.")
        link = link.strip()
        provider = next((p for p in state.providers if p.handles(link)), None)
        if provider is None:
            raise ApiError(422, "This link is not recognised. Supported: YouTube videos and playlists, "
                                "Spotify tracks, albums and playlists.")
        resolved = provider.resolve(link)
        resolve_id = state.remember(provider.name, resolved)
        mode = "audio" if provider.name == "spotify" else state.settings.mode
        items = []
        for index, item in enumerate(resolved.items):
            already = ""
            if state.store.find(item.provider, item.source_id, mode, ACTIVE):
                already = "in queue"
            else:
                done = state.store.find(item.provider, item.source_id, mode, ("done",))
                if done and done.file_path and Path(done.file_path).is_file():
                    already = "downloaded"
            items.append({
                "index": index,
                "title": item.title,
                "artist": item.artist,
                "album": item.album,
                "duration_seconds": item.duration_seconds,
                "cover_url": item.cover_url,
                "already": already,
            })
        return {
            "resolve_id": resolve_id,
            "provider": provider.name,
            "kind": resolved.kind,
            "title": resolved.title,
            "cover_url": resolved.cover_url,
            "count": len(items),
            "items": items,
        }

    def candidates(request: Request, _body: dict):
        provider_name, resolved = state.recall(request.path_params["resolve_id"])
        index = request.path_params["index"]
        if provider_name != "spotify":
            raise ApiError(422, "Only Spotify tracks have matches to choose from.")
        if not 0 <= index < len(resolved.items):
            raise ApiError(404, "No such item.")
        found = state.provider("spotify").candidates(resolved.items[index])
        return [asdict(candidate) for candidate in found]

    # ---- queue -----------------------------------------------------------

    def add_to_queue(_request: Request, body: dict):
        resolve_id = body.get("resolve_id")
        if not _is_int(resolve_id):
            raise ApiError(422, "resolve_id is missing.")
        mode = _choice(body, "mode", _MODES, "audio")
        audio_format = _choice(body, "audio_format", _AUDIO_FORMATS, "original")
        video_quality = _choice(body, "video_quality", _VIDEO_QUALITIES, "best")
        force = body.get("force", False)
        if not isinstance(force, bool):
            raise ApiError(422, "force must be true or false.")

        _provider_name, resolved = state.recall(resolve_id)
        total = len(resolved.items)
        indexes = body.get("indexes")  # missing means every item of the link
        if indexes is None:
            indexes = list(range(total))
        elif not isinstance(indexes, list) or any(not _is_int(i) or not 0 <= i < total for i in indexes):
            raise ApiError(422, "The selection contains an item that does not exist.")

        raw_matches = body.get("matches", {})  # item number -> chosen YouTube video ID
        if not isinstance(raw_matches, dict):
            raise ApiError(422, "A chosen match is not valid.")
        matches: dict[int, str] = {}
        for key, video_id in raw_matches.items():
            if not str(key).isdigit() or not 0 <= int(key) < total or not isinstance(video_id, str) or not _VIDEO_ID.match(video_id):
                raise ApiError(422, "A chosen match is not valid.")
            matches[int(key)] = video_id

        items = [replace(resolved.items[i], match_id=matches.get(i, "")) for i in dict.fromkeys(indexes)]
        group = resolved.title if resolved.kind in ("playlist", "album") else ""
        added = state.queue.add(items, mode, audio_format, video_quality, group, force=force)

        # Remember the last choice for next time.
        if (state.settings.mode, state.settings.audio_format, state.settings.video_quality) != (mode, audio_format, video_quality):
            state.settings.mode, state.settings.audio_format, state.settings.video_quality = mode, audio_format, video_quality
            config.save(state.settings, state.settings_file)
        return {
            "queued": sum(1 for entry in added if entry.result == "queued"),
            "skipped": sum(1 for entry in added if entry.result != "queued"),
            "jobs": [{**entry.job.summary(), "result": entry.result} for entry in added],
        }

    def get_queue(_request: Request, _body: dict):
        return [job.summary() for job in state.store.list(ACTIVE, limit=5000)]

    def pause_all(_request: Request, _body: dict):
        state.queue.pause_all()
        return {"ok": True}

    def resume_all(_request: Request, _body: dict):
        state.queue.resume_all()
        return {"ok": True}

    def job_action(request: Request, _body: dict):
        job_id = request.path_params["job_id"]
        action = request.path_params["action"]
        job = state.store.get(job_id)
        if job is None:
            raise ApiError(404, "No such download.")
        if action == "reveal":
            # The path comes from the history, never from the request.
            if not job.file_path or not Path(job.file_path).is_file():
                raise ApiError(404, "The file is no longer there.")
            subprocess.Popen(["explorer", "/select,", str(Path(job.file_path))])
            return {"ok": True}
        actions = {"pause": state.queue.pause, "resume": state.queue.resume,
                   "cancel": state.queue.cancel, "retry": state.queue.retry}
        if action not in actions:
            raise ApiError(404, "Unknown action.")
        actions[action](job_id)
        return state.store.get(job_id).summary()

    def job_matches(request: Request, _body: dict):
        """Other YouTube Music recordings for a Spotify song in the queue or the history."""
        job = state.store.get(request.path_params["job_id"])
        if job is None:
            raise ApiError(404, "No such download.")
        if job.item.provider != "spotify":
            raise ApiError(422, "Only Spotify songs have matches to choose from.")
        found = state.provider("spotify").candidates(job.item)
        return [{**asdict(c), "chosen": c.video_id == job.item.match_id} for c in found]

    def job_rematch(request: Request, body: dict):
        video_id = body.get("video_id")
        if not isinstance(video_id, str) or not _VIDEO_ID.match(video_id):
            raise ApiError(422, "A chosen match is not valid.")
        if not state.queue.rematch(request.path_params["job_id"], video_id):
            raise ApiError(422, "Only a finished or failed Spotify song can get another match.")
        return state.store.get(request.path_params["job_id"]).summary()

    def listen(_request: Request, body: dict):
        """Open a YouTube Music recording in the browser, to hear it before picking it."""
        video_id = body.get("video_id")
        if not isinstance(video_id, str) or not _VIDEO_ID.match(video_id):
            raise ApiError(422, "Not a valid video.")
        # The address is built here from a checked ID, never taken from the request.
        webbrowser.open(f"https://music.youtube.com/watch?v={video_id}")
        return {"ok": True}

    def update_check(_request: Request, _body: dict):
        try:
            return updater.check()
        except updater.UpdateError as exc:
            raise ApiError(422, str(exc)) from None

    def update_start(_request: Request, _body: dict):
        """Starts the updater in its own window. The UI closes the app right after this answer."""
        try:
            updater.start_update(os.getpid())
        except updater.UpdateError as exc:
            raise ApiError(422, str(exc)) from None
        return {"ok": True}

    def youtube_login_test(_request: Request, _body: dict):
        ok, message = test_login(state.provider("youtube"))
        return {"ok": ok, "message": message}

    # ---- history ---------------------------------------------------------

    def history(request: Request, _body: dict):
        search = request.query_params.get("search", "").strip()
        if len(search) > 200:
            raise ApiError(422, "The search text is too long.")
        limit = _query_int(request, "limit", 60, 1, 500)
        offset = _query_int(request, "offset", 0, 0, 10_000_000)
        statuses = ("failed",) if request.query_params.get("only") == "failed" else ("done", "failed")
        jobs = state.store.list(statuses, search=search, limit=limit, offset=offset, newest_first=True)
        return [job.summary() for job in jobs]

    def forget(request: Request, _body: dict):
        """Remove an entry from the history. The downloaded file is not touched."""
        job = state.store.get(request.path_params["job_id"])
        if job is None:
            raise ApiError(404, "No such entry.")
        if job.status in ACTIVE:
            raise ApiError(422, "Cancel the download first.")
        state.store.delete(job.id)
        return {"ok": True}

    # ---- live events -----------------------------------------------------

    async def events(request: Request):
        try:
            check_access(request)
        except ApiError as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status)
        client = state.hub.subscribe()

        async def stream():
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(client.get(), timeout=_HEARTBEAT_SECONDS)
                    except TimeoutError:
                        # A comment line keeps the connection open; it costs nothing and the UI ignores it.
                        if await request.is_disconnected():
                            return
                        yield ": ping\n\n"
                        continue
                    if event is None:  # the app is shutting down
                        return
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            finally:
                state.hub.unsubscribe(client)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---- cover pictures and the UI's own files ---------------------------

    async def cover(request: Request):
        try:
            check_access(request)
        except ApiError as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status)
        path = await run_in_threadpool(covers.thumbnail, request.query_params.get("u", ""), state.ffmpeg_path,
                                         request.query_params.get("shape") == "wide")
        if path is None:
            return Response(status_code=404)
        # A cover never changes, so the window may keep it and never ask again.
        return FileResponse(path, media_type="image/jpeg",
                            headers={"Cache-Control": "private, max-age=31536000, immutable"})

    async def index(_request: Request):
        # The page itself holds no secrets: the token arrives separately, in the window's address.
        # The policy line forbids the page from loading or contacting anything outside this app.
        policy = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                  "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'")
        return FileResponse(state.ui_dir / "index.html", media_type="text/html",
                            headers={"Cache-Control": "no-cache", "Content-Security-Policy": policy,
                                     "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        state.hub.attach(asyncio.get_running_loop())
        state.queue.start()
        yield
        # Running downloads go back to the queue and continue at the next start.
        await run_in_threadpool(state.queue.close)

    routes = [
        route("/api/status", "GET", status),
        route("/api/settings", "GET", get_settings),
        route("/api/settings", "PUT", put_settings, with_body=True),
        route("/api/spotify/login", "POST", spotify_login),
        route("/api/spotify/logout", "POST", spotify_logout),
        route("/api/resolve", "POST", resolve, with_body=True),
        route("/api/resolve/{resolve_id:int}/items/{index:int}/candidates", "GET", candidates),
        route("/api/queue", "POST", add_to_queue, with_body=True),
        route("/api/queue", "GET", get_queue),
        route("/api/queue/pause-all", "POST", pause_all),
        route("/api/queue/resume-all", "POST", resume_all),
        route("/api/jobs/{job_id:int}/matches", "GET", job_matches),
        route("/api/jobs/{job_id:int}/rematch", "POST", job_rematch, with_body=True),  # before the general one below
        route("/api/jobs/{job_id:int}/{action}", "POST", job_action),
        route("/api/listen", "POST", listen, with_body=True),
        route("/api/update", "GET", update_check),
        route("/api/youtube-login/test", "POST", youtube_login_test),
        route("/api/update", "POST", update_start),
        route("/api/history", "GET", history),
        route("/api/history/{job_id:int}", "DELETE", forget),
        Route("/api/events", events, methods=["GET"]),
        Route("/api/cover", cover, methods=["GET"]),
    ]
    if state.ui_dir is not None and (state.ui_dir / "index.html").is_file():
        routes.append(Route("/", index, methods=["GET"]))
        routes.append(Mount("/assets", StaticFiles(directory=state.ui_dir / "assets")))
    return Starlette(routes=routes, lifespan=lifespan)
