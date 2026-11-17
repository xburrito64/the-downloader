"""The download queue: a few worker threads that take jobs from the store.

Threads are used because yt-dlp and ffmpeg block while they work. The workers
sleep without using any CPU when the queue is empty.
"""

import glob
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import naming
from .config import Settings
from .errors import explain
from .providers.base import DownloadOptions, Item, Progress, ProviderError, Stopped
from .store import ACTIVE, Job, Store

Listener = Callable[[dict], None]


@dataclass
class Added:
    job: Job
    result: str  # "queued", "already downloaded" or "already in queue"


class DownloadQueue:
    retry_delay = 3.0  # seconds to wait before the one automatic second attempt

    def __init__(self, store: Store, providers: dict, settings: Settings, listener: Listener | None = None) -> None:
        self._store = store
        self._providers = providers
        self._settings = settings
        self._listener = listener
        self._wake = threading.Condition()
        self._closing = False
        self._threads: list[threading.Thread] = []
        self._workers: dict[int, threading.Thread] = {}  # worker number -> its thread
        self._limit = 1
        self._started = False
        # For each running job: why it should stop ("" = keep going).
        self._stop_reason: dict[int, str] = {}
        self._running = 0

    # ---- events ----------------------------------------------------------

    def _emit(self, event: dict) -> None:
        if self._listener is None:
            return
        try:
            self._listener(event)
        except Exception:
            pass  # a problem in the UI must never stop a download

    def _emit_job(self, job: Job | None) -> None:
        if job is not None:
            self._emit({"type": "job", "job": job.summary()})

    # ---- adding ----------------------------------------------------------

    def _target_for(self, item: Item) -> str:
        template = self._settings.spotify_template if item.provider == "spotify" else self._settings.youtube_template
        target = self._settings.output_path(item.provider) / naming.render(template, item)
        # Two different items can produce the same name (two videos both called "Intro").
        # The second one gets its ID added so it cannot be mistaken for the first.
        if self._store.target_used_by_other(str(target), item.provider, item.source_id):
            target = target.with_name(f"{target.name} [{naming.safe_name(item.source_id)}]")
        return str(target)

    def add(self, items: list[Item], mode: str, audio_format: str, video_quality: str,
            group_title: str = "", force: bool = False) -> list[Added]:
        """Queue items. Anything already downloaded or already waiting is skipped unless force is set."""
        results: list[Added] = []
        for item in items:
            # Spotify is audio only, so the video setting must not create a second copy.
            item_mode = "audio" if item.provider == "spotify" else mode
            if not force:
                waiting = self._store.find(item.provider, item.source_id, item_mode, ACTIVE)
                if waiting is not None:
                    results.append(Added(waiting, "already in queue"))
                    continue
                done = self._store.find(item.provider, item.source_id, item_mode, ("done",))
                # Only skip while the file is really still there. A deleted file can be downloaded again.
                if done is not None and done.file_path and Path(done.file_path).is_file():
                    job = self._store.add(item, item_mode, audio_format, video_quality, done.target, group_title,
                                          status="skipped", file_path=done.file_path)
                    results.append(Added(job, "already downloaded"))
                    self._emit_job(job)
                    continue
            job = self._store.add(item, item_mode, audio_format, video_quality, self._target_for(item), group_title)
            results.append(Added(job, "queued"))
            self._emit_job(job)
        with self._wake:
            self._wake.notify_all()
        return results

    # ---- controls --------------------------------------------------------

    def pause(self, job_id: int) -> None:
        """Stop a download but keep the partial file, so it can continue later."""
        with self._wake:
            if job_id in self._stop_reason:
                self._stop_reason[job_id] = "paused"
                return
        self._emit_job(self._store.set_status(job_id, "paused", only_if=("queued",)))

    def resume(self, job_id: int) -> None:
        self._requeue(job_id, ("paused",))

    def retry(self, job_id: int) -> None:
        self._requeue(job_id, ("failed", "cancelled"))

    def _requeue(self, job_id: int, only_if: tuple[str, ...]) -> None:
        job = self._store.set_status(job_id, "queued", only_if=only_if)
        self._emit_job(job)
        if job is not None:
            with self._wake:
                self._wake.notify_all()

    def cancel(self, job_id: int) -> None:
        """Stop a download and delete its partial file."""
        with self._wake:
            if job_id in self._stop_reason:
                self._stop_reason[job_id] = "cancelled"
                return
        job = self._store.set_status(job_id, "cancelled", only_if=("queued", "paused"))
        if job is not None:
            _delete_partial_files(job.target)
            self._emit_job(job)

    def pause_all(self) -> None:
        for job in self._store.list(("queued", "running"), limit=100_000):
            self.pause(job.id)

    def resume_all(self) -> None:
        for job in self._store.list(("paused",), limit=100_000):
            self.resume(job.id)

    # ---- running ---------------------------------------------------------

    def start(self) -> None:
        if self._threads:
            return
        self._closing = False
        self._started = True
        self._store.requeue_interrupted()
        self.set_parallel(self._settings.max_parallel_downloads)

    def set_parallel(self, count: int) -> None:
        """Change how many downloads run at the same time. Works while the queue is running.

        More: extra workers start at once. Fewer: the extra workers finish what they
        are downloading and then stop; nothing is interrupted.
        """
        with self._wake:
            self._limit = max(1, min(8, count))
            if not self._started or self._closing:
                return
            for number in range(self._limit):
                if number not in self._workers:
                    thread = threading.Thread(target=self._work, args=(number,), name=f"download-{number + 1}", daemon=True)
                    self._workers[number] = thread
                    thread.start()
            self._threads = list(self._workers.values())
            self._wake.notify_all()

    def close(self) -> None:
        """Stop the workers. Running downloads go back to the queue and continue next time."""
        with self._wake:
            self._closing = True
            for job_id in self._stop_reason:
                self._stop_reason[job_id] = self._stop_reason[job_id] or "closing"
            threads = list(self._workers.values())
            self._wake.notify_all()
        for thread in threads:
            thread.join(timeout=30)
        self._threads.clear()
        self._started = False

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Block until nothing is queued or running. Used by the terminal commands and tests."""
        with self._wake:
            return self._wake.wait_for(
                lambda: self._running == 0 and self._store.count(("queued", "running")) == 0, timeout
            )

    def _work(self, number: int) -> None:
        while True:
            with self._wake:
                if self._closing or number >= self._limit:
                    self._workers.pop(number, None)
                    return
                job = self._store.claim_next()
                if job is None:
                    self._wake.wait(timeout=5)  # sleeps; woken at once when something is added
                    continue
                self._stop_reason[job.id] = ""
                self._running += 1
            try:
                self._run(job)
            finally:
                with self._wake:
                    self._stop_reason.pop(job.id, None)
                    self._running -= 1
                    self._wake.notify_all()

    def _run(self, job: Job) -> None:
        self._emit_job(job)

        def on_progress(progress: Progress) -> None:
            self._emit({
                "type": "progress",
                "id": job.id,
                "fraction": progress.fraction,
                "speed": progress.speed_bytes_per_second,
                "stage": progress.stage,
            })

        options = DownloadOptions(job.mode, job.audio_format, job.video_quality, Path(job.target))
        # Every kind of failure ends here as a status on this one job. Nothing can escape
        # and stop the worker, so one bad track never stops the rest of the queue.
        def should_stop() -> bool:
            return bool(self._stop_reason.get(job.id))

        try:
            provider = self._providers[job.provider]
            try:
                path = provider.download(job.item, options, on_progress, should_stop)
            except ProviderError:
                # Some failures are passing network or YouTube hiccups. Try once more after
                # a short wait before calling it failed. A second failure is final.
                waited = 0.0
                while waited < self.retry_delay:
                    if should_stop():
                        raise Stopped() from None
                    time.sleep(0.1)
                    waited += 0.1
                path = provider.download(job.item, options, on_progress, should_stop)
        except Stopped:
            reason = self._stop_reason.get(job.id) or "paused"
            if reason == "cancelled":
                _delete_partial_files(job.target)
                self._emit_job(self._store.set_status(job.id, "cancelled"))
            elif reason == "closing":
                self._store.set_status(job.id, "queued")
            else:
                self._emit_job(self._store.set_status(job.id, "paused"))
        except ProviderError as exc:
            self._emit_job(self._store.set_status(job.id, "failed", error=str(exc)))
        except Exception as exc:
            self._emit_job(self._store.set_status(job.id, "failed", error=explain(f"Unexpected error: {exc}")))
        else:
            self._emit_job(self._store.set_status(job.id, "done", file_path=str(path)))


def _delete_partial_files(target: str) -> None:
    """Remove the unfinished pieces yt-dlp leaves behind for a cancelled download."""
    base = Path(target)
    for found in glob.glob(glob.escape(str(base)) + ".*"):
        path = Path(found)
        if path.suffix in (".part", ".ytdl") or ".part-Frag" in path.name:
            try:
                path.unlink()
            except OSError:
                pass
