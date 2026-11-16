"""SQLite storage: one table holds both the queue and the history.

A job starts as "queued" and ends as "done", "failed", "cancelled" or "skipped".
Finished jobs are the history. Progress is never written here; it changes many
times per second and only matters while the app is open.
"""

import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import paths
from .providers.base import Item

ACTIVE = ("queued", "running", "paused")
FINISHED = ("done", "failed", "cancelled", "skipped")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    provider      TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    mode          TEXT NOT NULL,
    audio_format  TEXT NOT NULL,
    video_quality TEXT NOT NULL,
    title         TEXT NOT NULL,
    artist        TEXT NOT NULL,
    group_title   TEXT NOT NULL,
    item_json     TEXT NOT NULL,
    target        TEXT NOT NULL,
    status        TEXT NOT NULL,
    error         TEXT NOT NULL DEFAULT '',
    file_path     TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL,
    finished_at   REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS jobs_by_source ON jobs (provider, source_id, mode);
CREATE INDEX IF NOT EXISTS jobs_by_status ON jobs (status);
"""


@dataclass
class Job:
    id: int
    provider: str
    source_id: str
    mode: str
    audio_format: str
    video_quality: str
    title: str
    artist: str
    group_title: str
    item: Item
    target: str  # full path without file extension
    status: str
    error: str
    file_path: str
    created_at: float
    finished_at: float

    def summary(self) -> dict:
        """What the UI needs to show a row."""
        return {
            "id": self.id,
            "provider": self.provider,
            "title": self.title,
            "artist": self.artist,
            "group": self.group_title,
            "cover_url": self.item.cover_url,
            "duration_seconds": self.item.duration_seconds,
            "mode": self.mode,
            "status": self.status,
            "error": self.error,
            "file_path": self.file_path,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


def _to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        provider=row["provider"],
        source_id=row["source_id"],
        mode=row["mode"],
        audio_format=row["audio_format"],
        video_quality=row["video_quality"],
        title=row["title"],
        artist=row["artist"],
        group_title=row["group_title"],
        item=Item(**json.loads(row["item_json"])),
        target=row["target"],
        status=row["status"],
        error=row["error"],
        file_path=row["file_path"],
        created_at=row["created_at"],
        finished_at=row["finished_at"],
    )


class Store:
    def __init__(self, file: Path | None = None) -> None:
        file = file or (paths.data_dir() / "library.sqlite")
        file.parent.mkdir(parents=True, exist_ok=True)
        # One connection shared by all threads, guarded by a lock. The queue writes a
        # few rows per download, so this is simpler and lighter than a connection per thread.
        self._db = sqlite3.connect(file, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")  # readers never block the writer
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ---- writing ---------------------------------------------------------

    def add(self, item: Item, mode: str, audio_format: str, video_quality: str, target: str,
            group_title: str = "", status: str = "queued", file_path: str = "") -> Job:
        now = time.time()
        with self._lock:
            cursor = self._db.execute(
                "INSERT INTO jobs (provider, source_id, mode, audio_format, video_quality, title, artist, group_title,"
                " item_json, target, status, file_path, created_at, finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.provider, item.source_id, mode, audio_format, video_quality, item.title, item.artist, group_title,
                 json.dumps(asdict(item)), target, status, file_path, now, now if status in FINISHED else 0),
            )
            row = self._db.execute("SELECT * FROM jobs WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return _to_job(row)

    def claim_next(self) -> Job | None:
        """Take the oldest queued job and mark it running, as one step."""
        with self._lock:
            row = self._db.execute(
                "UPDATE jobs SET status = 'running', error = '' WHERE id = "
                "(SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1) RETURNING *"
            ).fetchone()
        return _to_job(row) if row else None

    def set_status(self, job_id: int, status: str, error: str = "", file_path: str | None = None,
                   only_if: tuple[str, ...] | None = None) -> Job | None:
        """Change a job's status. With only_if, nothing happens unless the job is in one of those states."""
        finished_at = time.time() if status in FINISHED else 0
        query = "UPDATE jobs SET status = ?, error = ?, finished_at = ?"
        values: list = [status, error, finished_at]
        if file_path is not None:
            query += ", file_path = ?"
            values.append(file_path)
        query += " WHERE id = ?"
        values.append(job_id)
        if only_if:
            query += f" AND status IN ({','.join('?' * len(only_if))})"
            values.extend(only_if)
        with self._lock:
            row = self._db.execute(query + " RETURNING *", values).fetchone()
        return _to_job(row) if row else None

    def requeue_interrupted(self) -> int:
        """Jobs left "running" by a crash or a closed app go back to the queue."""
        with self._lock:
            return self._db.execute("UPDATE jobs SET status = 'queued' WHERE status = 'running'").rowcount

    def delete(self, job_id: int) -> None:
        with self._lock:
            self._db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    # ---- reading ---------------------------------------------------------

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _to_job(row) if row else None

    def find(self, provider: str, source_id: str, mode: str, statuses: tuple[str, ...]) -> Job | None:
        """The newest job for the same thing (same source and same audio/video choice)."""
        marks = ",".join("?" * len(statuses))
        with self._lock:
            row = self._db.execute(
                f"SELECT * FROM jobs WHERE provider = ? AND source_id = ? AND mode = ? AND status IN ({marks})"
                " ORDER BY id DESC LIMIT 1",
                (provider, source_id, mode, *statuses),
            ).fetchone()
        return _to_job(row) if row else None

    def target_used_by_other(self, target: str, provider: str, source_id: str) -> bool:
        """True when a different item already uses this file name."""
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM jobs WHERE target = ? COLLATE NOCASE AND NOT (provider = ? AND source_id = ?)"
                " AND status IN ('queued','running','paused','done') LIMIT 1",
                (target, provider, source_id),
            ).fetchone()
        return row is not None

    def count(self, statuses: tuple[str, ...]) -> int:
        marks = ",".join("?" * len(statuses))
        with self._lock:
            return self._db.execute(f"SELECT COUNT(*) FROM jobs WHERE status IN ({marks})", statuses).fetchone()[0]

    def list(self, statuses: tuple[str, ...], search: str = "", limit: int = 200, offset: int = 0,
             newest_first: bool = False) -> list[Job]:
        marks = ",".join("?" * len(statuses))
        query = f"SELECT * FROM jobs WHERE status IN ({marks})"
        values: list = list(statuses)
        if search:
            like = f"%{search.replace('%', r'\%').replace('_', r'\_')}%"
            query += r" AND (title LIKE ? ESCAPE '\' OR artist LIKE ? ESCAPE '\' OR group_title LIKE ? ESCAPE '\')"
            values += [like, like, like]
        query += f" ORDER BY {'finished_at DESC, id DESC' if newest_first else 'id'} LIMIT ? OFFSET ?"
        values += [limit, offset]
        with self._lock:
            rows = self._db.execute(query, values).fetchall()
        return [_to_job(row) for row in rows]
