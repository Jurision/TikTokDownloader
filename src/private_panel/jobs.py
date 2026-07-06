from collections.abc import Iterator
from contextlib import contextmanager
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .models import JobKind, JobRecord, JobStatus


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class JobStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        else:
            db.commit()
        finally:
            db.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_text TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    progress_total INTEGER NOT NULL DEFAULT 0,
                    progress_done INTEGER NOT NULL DEFAULT 0,
                    output_dir TEXT NOT NULL DEFAULT '',
                    log_tail TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT ''
                )
                """
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at)"
            )

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            kind=JobKind(row["kind"]),
            status=JobStatus(row["status"]),
            input_text=row["input_text"],
            platform=row["platform"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            progress_total=row["progress_total"],
            progress_done=row["progress_done"],
            output_dir=row["output_dir"],
            log_tail=row["log_tail"],
            error=row["error"],
        )

    def create_job(self, kind: JobKind, input_text: str) -> JobRecord:
        job_id = secrets.token_urlsafe(9)
        now = utc_now()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO jobs (id, kind, status, input_text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, kind.value, JobStatus.QUEUED.value, input_text, now),
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> JobRecord:
        with self._connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row_to_job(row)

    def list_jobs(self, limit: int = 50) -> list[JobRecord]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def claim_next_queued(self) -> JobRecord | None:
        with self._connect() as db:
            row = db.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = ?
                WHERE rowid = (
                    SELECT rowid FROM jobs
                    WHERE status = ?
                    ORDER BY created_at ASC, rowid ASC
                    LIMIT 1
                )
                RETURNING *
                """,
                (JobStatus.RUNNING.value, utc_now(), JobStatus.QUEUED.value),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_job(row)

    def mark_succeeded(self, job_id: str, output_dir: str, log_tail: str = "") -> None:
        self._finish(
            job_id,
            JobStatus.SUCCEEDED,
            output_dir=output_dir,
            log_tail=log_tail,
            error="",
        )

    def mark_failed(self, job_id: str, error: str, log_tail: str = "") -> None:
        self._finish(
            job_id,
            JobStatus.FAILED,
            output_dir="",
            log_tail=log_tail,
            error=error,
        )

    def update_progress(
        self,
        job_id: str,
        progress_done: int,
        progress_total: int,
        log_tail: str = "",
    ) -> None:
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE jobs
                SET progress_done = ?, progress_total = ?, log_tail = ?
                WHERE id = ?
                """,
                (progress_done, progress_total, log_tail, job_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(job_id)

    def _finish(
        self,
        job_id: str,
        status: JobStatus,
        output_dir: str,
        log_tail: str,
        error: str,
    ) -> None:
        now = utc_now()
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, output_dir = ?, log_tail = ?, error = ?
                WHERE id = ?
                """,
                (status.value, now, output_dir, log_tail, error, job_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(job_id)
