# Private Download Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a navi-gated personal download panel that can submit, track, and retrieve private Douyin/TikTok download jobs.

**Architecture:** Add a focused `src/private_panel` package beside the existing application layer. The panel owns auth, job state, worker orchestration, file listing, and HTTP UI/API routes; actual media parsing and downloading stays delegated to existing DouK-Downloader core code. The deployed service stays internal-only behind Caddy/navi and only uses token auth for script/API access.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLite, `unittest`, existing DouK-Downloader modules, Docker Compose, Caddy forward_auth.

---

## Scope

This plan implements the first slice from `docs/superpowers/specs/2026-07-06-private-download-panel-design.md`:

- Private panel app shell.
- Navi identity header and token auth.
- SQLite job store.
- Single worker skeleton.
- Single-link Douyin download executor adapter.
- Job file listing and download boundary checks.
- Docker Compose and Caddy deployment notes.

Account liked works, logged-in favorites, and mix downloads are represented in the model enum so the UI can show future choices, but only `douyin_single` is wired to a real executor in this slice. Unsupported kinds should fail clearly as unsupported instead of silently doing nothing.

## File Structure

- Create `src/private_panel/__init__.py`: package marker and exported factory.
- Create `src/private_panel/models.py`: enums and Pydantic models shared by auth, job store, worker, and app routes.
- Create `src/private_panel/auth.py`: navi identity header parsing and `DOUK_PRIVATE_TOKEN` verification.
- Create `src/private_panel/jobs.py`: SQLite-backed job persistence and status transitions.
- Create `src/private_panel/files.py`: safe file listing and path resolution rooted under panel output directories.
- Create `src/private_panel/executor.py`: job execution dispatch, including the first Douyin single-link adapter.
- Create `src/private_panel/worker.py`: single-concurrency background worker.
- Create `src/private_panel/app.py`: FastAPI routes for UI, API, health, job submission, job detail, and files.
- Modify `main.py`: launch panel mode when `DOUK_PANEL_MODE=1`.
- Create `src/private_panel/tests/`: unit tests for each boundary.
- Create `deploy/private-panel/`: Compose, env example, and deployment notes.

## Shared Commands

Run focused tests from the repository root:

```powershell
python -m unittest src.private_panel.tests.test_auth -v
python -m unittest src.private_panel.tests.test_jobs -v
python -m unittest src.private_panel.tests.test_files -v
python -m unittest src.private_panel.tests.test_executor_worker -v
python -m unittest src.private_panel.tests.test_app -v
python -m unittest src.private_panel.tests.test_main_panel_mode -v
python -m unittest src.private_panel.tests.test_deploy_private_panel -v
```

Run all private panel tests:

```powershell
python -m unittest discover -s src/private_panel/tests -v
```

Run the existing automation regression suite:

```powershell
python -m unittest automation.tests.test_prepare_douyin_sync -v
```

### Task 1: Auth And Shared Models

**Files:**
- Create: `src/private_panel/__init__.py`
- Create: `src/private_panel/models.py`
- Create: `src/private_panel/auth.py`
- Create: `src/private_panel/tests/__init__.py`
- Test: `src/private_panel/tests/test_auth.py`

- [ ] **Step 1: Write the failing auth/model tests**

Create `src/private_panel/tests/__init__.py` as an empty file.

Create `src/private_panel/tests/test_auth.py`:

```python
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from src.private_panel.auth import (
    extract_bearer_token,
    require_panel_user,
    token_matches,
    user_from_navi_headers,
)
from src.private_panel.models import JobKind, JobStatus, PanelUser


class PrivatePanelAuthTests(unittest.IsolatedAsyncioTestCase):
    def test_models_include_first_slice_job_kinds(self):
        self.assertEqual(JobKind.DOUYIN_SINGLE.value, "douyin_single")
        self.assertEqual(JobKind.DOUYIN_FAVORITES.value, "douyin_favorites")
        self.assertEqual(JobKind.TIKTOK_SINGLE.value, "tiktok_single")
        self.assertEqual(JobStatus.QUEUED.value, "queued")
        self.assertEqual(JobStatus.RUNNING.value, "running")
        self.assertEqual(JobStatus.SUCCEEDED.value, "succeeded")
        self.assertEqual(JobStatus.FAILED.value, "failed")

    def test_navi_headers_create_panel_user(self):
        user = user_from_navi_headers(
            "user-123",
            "owner@example.com",
            "Owner",
        )

        self.assertEqual(
            user,
            PanelUser(
                id="user-123",
                email="owner@example.com",
                name="Owner",
                via="navi",
            ),
        )

    def test_navi_header_values_are_sanitized(self):
        user = user_from_navi_headers(
            "user\r\nbad",
            "owner@example.com",
            "Owner\nName",
        )

        self.assertEqual(user.id, "user bad")
        self.assertEqual(user.name, "Owner Name")

    def test_missing_navi_user_returns_none(self):
        self.assertIsNone(user_from_navi_headers("", "", ""))

    def test_extract_bearer_token_accepts_bearer_header(self):
        self.assertEqual(extract_bearer_token("Bearer abc123"), "abc123")
        self.assertEqual(extract_bearer_token("bearer abc123"), "abc123")
        self.assertEqual(extract_bearer_token("Token abc123"), "")

    def test_token_matches_uses_constant_time_compare(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            self.assertTrue(token_matches("secret"))
            self.assertFalse(token_matches("wrong"))
            self.assertFalse(token_matches(""))

    def test_token_auth_is_disabled_when_env_token_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(token_matches("secret"))

    async def test_require_panel_user_prefers_navi_identity(self):
        user = await require_panel_user(
            authorization="Bearer wrong",
            x_douk_token="wrong",
            x_tradedocs_user_id="user-123",
            x_tradedocs_user_email="owner@example.com",
            x_tradedocs_user_name="Owner",
        )

        self.assertEqual(user.via, "navi")
        self.assertEqual(user.id, "user-123")

    async def test_require_panel_user_accepts_private_token(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            user = await require_panel_user(
                authorization="Bearer secret",
                x_douk_token="",
                x_tradedocs_user_id="",
                x_tradedocs_user_email="",
                x_tradedocs_user_name="",
            )

        self.assertEqual(user.via, "token")
        self.assertEqual(user.id, "token")

    async def test_require_panel_user_rejects_unauthenticated_request(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                await require_panel_user(
                    authorization="Bearer wrong",
                    x_douk_token="",
                    x_tradedocs_user_id="",
                    x_tradedocs_user_email="",
                    x_tradedocs_user_name="",
                )

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m unittest src.private_panel.tests.test_auth -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.private_panel'`.

- [ ] **Step 3: Add shared models and auth implementation**

Create `src/private_panel/__init__.py`:

```python
__all__ = []
```

Create `src/private_panel/models.py`:

```python
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class JobKind(StrEnum):
    AUTO = "auto"
    DOUYIN_ACCOUNT_POSTS = "douyin_account_posts"
    DOUYIN_ACCOUNT_LIKED = "douyin_account_liked"
    DOUYIN_SINGLE = "douyin_single"
    DOUYIN_MIX = "douyin_mix"
    DOUYIN_FAVORITES = "douyin_favorites"
    TIKTOK_ACCOUNT_POSTS = "tiktok_account_posts"
    TIKTOK_ACCOUNT_LIKED = "tiktok_account_liked"
    TIKTOK_SINGLE = "tiktok_single"
    TIKTOK_MIX = "tiktok_mix"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PanelUser(BaseModel):
    id: str
    email: str = ""
    name: str = ""
    via: Literal["navi", "token"]


class JobCreate(BaseModel):
    kind: JobKind = JobKind.AUTO
    input_text: str = Field("", max_length=12000)


class JobRecord(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus
    input_text: str
    platform: str = ""
    created_at: str
    started_at: str = ""
    finished_at: str = ""
    progress_total: int = 0
    progress_done: int = 0
    output_dir: str = ""
    log_tail: str = ""
    error: str = ""


class FileEntry(BaseModel):
    name: str
    relative_path: str
    size: int
    modified_at: str
```

Create `src/private_panel/auth.py`:

```python
import hmac
import os

from fastapi import Header, HTTPException

from .models import PanelUser


def _clean_header(value: str, fallback: str = "") -> str:
    text = str(value or fallback).replace("\r", " ").replace("\n", " ").strip()
    return text[:160]


def user_from_navi_headers(
    user_id: str = "",
    user_email: str = "",
    user_name: str = "",
) -> PanelUser | None:
    clean_id = _clean_header(user_id)
    if not clean_id:
        return None
    return PanelUser(
        id=clean_id,
        email=_clean_header(user_email),
        name=_clean_header(user_name),
        via="navi",
    )


def extract_bearer_token(authorization: str = "") -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return ""
    return token.strip()


def token_matches(token: str) -> bool:
    expected = os.environ.get("DOUK_PRIVATE_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


async def require_panel_user(
    authorization: str = Header("", alias="Authorization"),
    x_douk_token: str = Header("", alias="X-Douk-Token"),
    x_tradedocs_user_id: str = Header("", alias="X-Tradedocs-User-Id"),
    x_tradedocs_user_email: str = Header("", alias="X-Tradedocs-User-Email"),
    x_tradedocs_user_name: str = Header("", alias="X-Tradedocs-User-Name"),
) -> PanelUser:
    if user := user_from_navi_headers(
        x_tradedocs_user_id,
        x_tradedocs_user_email,
        x_tradedocs_user_name,
    ):
        return user

    token = x_douk_token or extract_bearer_token(authorization)
    if token_matches(token):
        return PanelUser(id="token", name="Private API", via="token")

    raise HTTPException(status_code=401, detail="Authentication required")
```

- [ ] **Step 4: Run the auth tests to verify they pass**

Run:

```powershell
python -m unittest src.private_panel.tests.test_auth -v
```

Expected: PASS, all tests in `PrivatePanelAuthTests`.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/private_panel
git commit -m "feat: add private panel auth models"
```

### Task 2: SQLite Job Store

**Files:**
- Create: `src/private_panel/jobs.py`
- Test: `src/private_panel/tests/test_jobs.py`

- [ ] **Step 1: Write the failing job store tests**

Create `src/private_panel/tests/test_jobs.py`:

```python
import tempfile
import unittest
from pathlib import Path

from src.private_panel.jobs import JobStore
from src.private_panel.models import JobKind, JobStatus


class PrivatePanelJobStoreTests(unittest.TestCase):
    def test_create_job_persists_queued_record(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")

            job = store.create_job(JobKind.DOUYIN_SINGLE, "https://v.douyin.com/abc/")
            loaded = store.get_job(job.id)

        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(loaded.id, job.id)
        self.assertEqual(loaded.kind, JobKind.DOUYIN_SINGLE)
        self.assertEqual(loaded.input_text, "https://v.douyin.com/abc/")
        self.assertTrue(loaded.created_at)

    def test_list_jobs_orders_newest_first(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            first = store.create_job(JobKind.DOUYIN_SINGLE, "one")
            second = store.create_job(JobKind.DOUYIN_SINGLE, "two")

            jobs = store.list_jobs()

        self.assertEqual([j.id for j in jobs], [second.id, first.id])

    def test_claim_next_queued_job_marks_running(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "one")

            claimed = store.claim_next_queued()
            loaded = store.get_job(created.id)

        self.assertEqual(claimed.id, created.id)
        self.assertEqual(claimed.status, JobStatus.RUNNING)
        self.assertEqual(loaded.status, JobStatus.RUNNING)
        self.assertTrue(loaded.started_at)

    def test_claim_next_queued_job_ignores_running_jobs(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            store.create_job(JobKind.DOUYIN_SINGLE, "one")
            store.claim_next_queued()

            claimed = store.claim_next_queued()

        self.assertIsNone(claimed)

    def test_mark_succeeded_sets_output_and_finished_time(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "one")
            store.claim_next_queued()

            store.mark_succeeded(created.id, output_dir="jobs/abc", log_tail="done")
            loaded = store.get_job(created.id)

        self.assertEqual(loaded.status, JobStatus.SUCCEEDED)
        self.assertEqual(loaded.output_dir, "jobs/abc")
        self.assertEqual(loaded.log_tail, "done")
        self.assertTrue(loaded.finished_at)

    def test_mark_failed_sets_error_and_finished_time(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "one")
            store.claim_next_queued()

            store.mark_failed(created.id, "cookie expired", log_tail="failed")
            loaded = store.get_job(created.id)

        self.assertEqual(loaded.status, JobStatus.FAILED)
        self.assertEqual(loaded.error, "cookie expired")
        self.assertEqual(loaded.log_tail, "failed")
        self.assertTrue(loaded.finished_at)

    def test_missing_job_raises_key_error(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")

            with self.assertRaises(KeyError):
                store.get_job("missing")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the job tests to verify they fail**

Run:

```powershell
python -m unittest src.private_panel.tests.test_jobs -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.private_panel.jobs'`.

- [ ] **Step 3: Add the SQLite job store**

Create `src/private_panel/jobs.py`:

```python
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

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

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
                "SELECT * FROM jobs ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def claim_next_queued(self) -> JobRecord | None:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                return None
            now = utc_now()
            db.execute(
                """
                UPDATE jobs
                SET status = ?, started_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    now,
                    row["id"],
                    JobStatus.QUEUED.value,
                ),
            )
        return self.get_job(row["id"])

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
            db.execute(
                """
                UPDATE jobs
                SET progress_done = ?, progress_total = ?, log_tail = ?
                WHERE id = ?
                """,
                (progress_done, progress_total, log_tail, job_id),
            )

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
            db.execute(
                """
                UPDATE jobs
                SET status = ?, finished_at = ?, output_dir = ?, log_tail = ?, error = ?
                WHERE id = ?
                """,
                (status.value, now, output_dir, log_tail, error, job_id),
            )
```

- [ ] **Step 4: Run the job tests to verify they pass**

Run:

```powershell
python -m unittest src.private_panel.tests.test_jobs -v
```

Expected: PASS, all tests in `PrivatePanelJobStoreTests`.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/private_panel/jobs.py src/private_panel/tests/test_jobs.py
git commit -m "feat: add private panel job store"
```

### Task 3: Safe File Listing

**Files:**
- Create: `src/private_panel/files.py`
- Test: `src/private_panel/tests/test_files.py`

- [ ] **Step 1: Write the failing file boundary tests**

Create `src/private_panel/tests/test_files.py`:

```python
import tempfile
import unittest
from pathlib import Path

from src.private_panel.files import list_files, resolve_job_file


class PrivatePanelFileTests(unittest.TestCase):
    def test_list_files_returns_relative_entries(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            job_dir = root / "jobs" / "abc"
            job_dir.mkdir(parents=True)
            file_path = job_dir / "video.mp4"
            file_path.write_bytes(b"abc")

            entries = list_files(root, "jobs/abc")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "video.mp4")
        self.assertEqual(entries[0].relative_path, "video.mp4")
        self.assertEqual(entries[0].size, 3)

    def test_list_files_ignores_directories(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            job_dir = root / "jobs" / "abc"
            (job_dir / "nested").mkdir(parents=True)

            entries = list_files(root, "jobs/abc")

        self.assertEqual(entries, [])

    def test_resolve_job_file_accepts_file_under_job_dir(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            job_dir = root / "jobs" / "abc"
            job_dir.mkdir(parents=True)
            file_path = job_dir / "video.mp4"
            file_path.write_bytes(b"abc")

            resolved = resolve_job_file(root, "jobs/abc", "video.mp4")

        self.assertEqual(resolved.name, "video.mp4")

    def test_resolve_job_file_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            job_dir = root / "jobs" / "abc"
            job_dir.mkdir(parents=True)
            (root / "secret.txt").write_text("secret", encoding="utf-8")

            with self.assertRaises(ValueError):
                resolve_job_file(root, "jobs/abc", "../secret.txt")

    def test_resolve_job_file_rejects_missing_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            (root / "jobs" / "abc").mkdir(parents=True)

            with self.assertRaises(FileNotFoundError):
                resolve_job_file(root, "jobs/abc", "missing.mp4")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the file tests to verify they fail**

Run:

```powershell
python -m unittest src.private_panel.tests.test_files -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.private_panel.files'`.

- [ ] **Step 3: Add safe file helpers**

Create `src/private_panel/files.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

from .models import FileEntry


def _resolve_under(root: Path, relative: str) -> Path:
    root_path = Path(root).resolve()
    target = root_path.joinpath(relative).resolve()
    if target != root_path and root_path not in target.parents:
        raise ValueError("Path escapes output root")
    return target


def _modified_at(path: Path) -> str:
    return (
        datetime.fromtimestamp(path.stat().st_mtime, UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def list_files(output_root: Path, output_dir: str) -> list[FileEntry]:
    directory = _resolve_under(output_root, output_dir)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError("Job output path is not a directory")
    entries = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(directory).as_posix()
        entries.append(
            FileEntry(
                name=path.name,
                relative_path=relative_path,
                size=path.stat().st_size,
                modified_at=_modified_at(path),
            )
        )
    return entries


def resolve_job_file(output_root: Path, output_dir: str, relative_path: str) -> Path:
    directory = _resolve_under(output_root, output_dir)
    target = directory.joinpath(relative_path).resolve()
    if target != directory and directory not in target.parents:
        raise ValueError("Path escapes job output directory")
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    return target
```

- [ ] **Step 4: Run the file tests to verify they pass**

Run:

```powershell
python -m unittest src.private_panel.tests.test_files -v
```

Expected: PASS, all tests in `PrivatePanelFileTests`.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/private_panel/files.py src/private_panel/tests/test_files.py
git commit -m "feat: add private panel file boundaries"
```

### Task 4: Executor Dispatch And Worker

**Files:**
- Create: `src/private_panel/executor.py`
- Create: `src/private_panel/worker.py`
- Test: `src/private_panel/tests/test_executor_worker.py`

- [ ] **Step 1: Write failing executor and worker tests**

Create `src/private_panel/tests/test_executor_worker.py`:

```python
import asyncio
import tempfile
import unittest
from pathlib import Path

from src.private_panel.executor import JobExecutionResult, PrivatePanelExecutor
from src.private_panel.jobs import JobStore
from src.private_panel.models import JobKind, JobStatus
from src.private_panel.worker import run_one_job


class RecordingExecutor(PrivatePanelExecutor):
    def __init__(self):
        super().__init__(volume_root=Path("."))
        self.seen = []

    async def download_douyin_single(self, job):
        self.seen.append(job.id)
        return JobExecutionResult(
            output_dir=f"jobs/{job.id}",
            log_tail="downloaded one douyin link",
        )


class FailingExecutor(PrivatePanelExecutor):
    def __init__(self):
        super().__init__(volume_root=Path("."))

    async def download_douyin_single(self, job):
        raise RuntimeError("cookie expired")


class PrivatePanelExecutorWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_executor_dispatches_douyin_single(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "https://v.douyin.com/abc/")
            job = store.claim_next_queued()
            executor = RecordingExecutor()

            result = await executor.execute(job)

        self.assertEqual(result.output_dir, f"jobs/{created.id}")
        self.assertEqual(result.log_tail, "downloaded one douyin link")
        self.assertEqual(executor.seen, [created.id])

    async def test_executor_rejects_unsupported_kind(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            store.create_job(JobKind.DOUYIN_FAVORITES, "")
            job = store.claim_next_queued()
            executor = PrivatePanelExecutor(volume_root=Path(temp))

            with self.assertRaises(NotImplementedError):
                await executor.execute(job)

    async def test_run_one_job_marks_success(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "https://v.douyin.com/abc/")
            executor = RecordingExecutor()

            processed = await run_one_job(store, executor)
            loaded = store.get_job(created.id)

        self.assertTrue(processed)
        self.assertEqual(loaded.status, JobStatus.SUCCEEDED)
        self.assertEqual(loaded.output_dir, f"jobs/{created.id}")
        self.assertEqual(loaded.log_tail, "downloaded one douyin link")

    async def test_run_one_job_marks_failure(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "https://v.douyin.com/abc/")
            executor = FailingExecutor()

            processed = await run_one_job(store, executor)
            loaded = store.get_job(created.id)

        self.assertTrue(processed)
        self.assertEqual(loaded.status, JobStatus.FAILED)
        self.assertEqual(loaded.error, "cookie expired")

    async def test_run_one_job_returns_false_when_queue_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")

            processed = await run_one_job(store, RecordingExecutor())

        self.assertFalse(processed)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
python -m unittest src.private_panel.tests.test_executor_worker -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.private_panel.executor'`.

- [ ] **Step 3: Add executor and worker skeleton with real Douyin single adapter**

Create `src/private_panel/executor.py`:

```python
from dataclasses import dataclass
from pathlib import Path

from src.application import TikTokDownloader
from src.application.main_terminal import TikTok

from .models import JobKind, JobRecord


@dataclass(frozen=True)
class JobExecutionResult:
    output_dir: str
    log_tail: str


class PrivatePanelExecutor:
    def __init__(self, volume_root: Path):
        self.volume_root = Path(volume_root)

    async def execute(self, job: JobRecord) -> JobExecutionResult:
        if job.kind == JobKind.DOUYIN_SINGLE:
            return await self.download_douyin_single(job)
        raise NotImplementedError(f"Unsupported job kind: {job.kind.value}")

    async def download_douyin_single(self, job: JobRecord) -> JobExecutionResult:
        job_output = self.volume_root / "private_panel" / "jobs" / job.id / "files"
        job_output.mkdir(parents=True, exist_ok=True)
        async with TikTokDownloader() as downloader:
            downloader.check_config()
            await downloader.check_settings(False)
            downloader.parameter.root = job_output
            downloader.parameter.folder_name = "Download"
            terminal = TikTok(downloader.parameter, downloader.database)
            root, params, logger = terminal.record.run(terminal.parameter)
            async with logger(root, console=terminal.console, **params) as record:
                ids = await terminal.links.run(job.input_text)
                if not any(ids):
                    raise ValueError("No Douyin work ID found in submitted text")
                preview = await terminal._handle_detail(ids, False, record)
                if not preview:
                    raise RuntimeError("Douyin single-link download returned no result")

        return JobExecutionResult(
            output_dir=f"private_panel/jobs/{job.id}/files",
            log_tail=f"Downloaded {len(ids)} Douyin work item(s)",
        )
```

Create `src/private_panel/worker.py`:

```python
import asyncio

from .executor import PrivatePanelExecutor
from .jobs import JobStore


async def run_one_job(store: JobStore, executor: PrivatePanelExecutor) -> bool:
    job = store.claim_next_queued()
    if job is None:
        return False
    try:
        result = await executor.execute(job)
    except Exception as exc:
        store.mark_failed(job.id, str(exc), log_tail=str(exc))
        return True
    store.mark_succeeded(job.id, result.output_dir, log_tail=result.log_tail)
    return True


async def worker_loop(
    store: JobStore,
    executor: PrivatePanelExecutor,
    poll_seconds: float = 2.0,
) -> None:
    while True:
        processed = await run_one_job(store, executor)
        if not processed:
            await asyncio.sleep(poll_seconds)
```

- [ ] **Step 4: Run executor/worker tests to verify they pass**

Run:

```powershell
python -m unittest src.private_panel.tests.test_executor_worker -v
```

Expected: PASS, all tests in `PrivatePanelExecutorWorkerTests`.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/private_panel/executor.py src/private_panel/worker.py src/private_panel/tests/test_executor_worker.py
git commit -m "feat: add private panel worker executor"
```

### Task 5: FastAPI Panel App And Minimal UI

**Files:**
- Create: `src/private_panel/app.py`
- Test: `src/private_panel/tests/test_app.py`

- [ ] **Step 1: Write failing app tests**

Create `src/private_panel/tests/test_app.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.private_panel.app import create_panel_app
from src.private_panel.models import JobStatus


class PrivatePanelAppTests(unittest.TestCase):
    def test_health_endpoint_is_public_and_minimal(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            response = client.get("/downloads/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "service": "private-download-panel"})

    def test_jobs_api_requires_auth(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            response = client.get("/downloads/api/jobs")

        self.assertEqual(response.status_code, 401)

    def test_submit_job_with_token_creates_queued_job(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            with patch.dict("os.environ", {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
                client = TestClient(create_panel_app(Path(temp)))
                response = client.post(
                    "/downloads/api/jobs",
                    headers={"Authorization": "Bearer secret"},
                    json={"kind": "douyin_single", "input_text": "https://v.douyin.com/abc/"},
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kind"], "douyin_single")
        self.assertEqual(data["status"], JobStatus.QUEUED.value)

    def test_jobs_api_accepts_navi_identity_headers(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))
            response = client.get(
                "/downloads/api/jobs",
                headers={"X-Tradedocs-User-Id": "user-123"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_panel_page_renders_tool_shell_for_navi_user(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))
            response = client.get(
                "/downloads/",
                headers={"X-Tradedocs-User-Id": "user-123", "X-Tradedocs-User-Name": "Owner"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Private Download Panel", response.text)
        self.assertIn("Owner", response.text)
        self.assertIn('fetch("/downloads/api/jobs"', response.text)

    def test_job_files_endpoint_lists_files_for_completed_job(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            output_dir = root / "jobs" / "abc"
            output_dir.mkdir(parents=True)
            (output_dir / "video.mp4").write_bytes(b"abc")
            client = TestClient(create_panel_app(root))
            created = client.post(
                "/downloads/api/jobs",
                headers={"X-Tradedocs-User-Id": "user-123"},
                json={"kind": "douyin_single", "input_text": "https://v.douyin.com/abc/"},
            ).json()
            app_store = client.app.state.job_store
            app_store.mark_succeeded(created["id"], "jobs/abc", "done")

            response = client.get(
                f"/downloads/api/jobs/{created['id']}/files",
                headers={"X-Tradedocs-User-Id": "user-123"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["relative_path"], "video.mp4")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run app tests to verify they fail**

Run:

```powershell
python -m unittest src.private_panel.tests.test_app -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.private_panel.app'`.

- [ ] **Step 3: Add FastAPI app, API routes, and minimal HTML**

Create `src/private_panel/app.py`:

```python
import html
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .auth import require_panel_user
from .files import list_files, resolve_job_file
from .jobs import JobStore
from .models import JobCreate, JobRecord, PanelUser


def _job_store(volume_root: Path) -> JobStore:
    return JobStore(Path(volume_root) / "private_panel" / "jobs.db")


def _panel_html(user: PanelUser, jobs: list[JobRecord]) -> str:
    rows = "\n".join(
        f"<tr><td>{html.escape(job.id)}</td><td>{html.escape(job.kind.value)}</td>"
        f"<td>{html.escape(job.status.value)}</td><td>{html.escape(job.log_tail)}</td></tr>"
        for job in jobs
    )
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Private Download Panel</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #18201b; }}
    main {{ max-width: 1040px; margin: 0 auto; }}
    textarea, select, button {{ font: inherit; }}
    textarea {{ width: 100%; min-height: 120px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
    th, td {{ border-bottom: 1px solid #d9e2dc; padding: 8px; text-align: left; }}
    button {{ padding: 8px 12px; background: #1d7f5f; color: white; border: 0; border-radius: 6px; }}
  </style>
</head>
<body>
<main>
  <h1>Private Download Panel</h1>
  <p>Signed in as {html.escape(user.name or user.id)}</p>
  <form id="job-form">
    <label for="kind">Source type</label>
    <select id="kind" name="kind">
      <option value="douyin_single">Douyin single work link</option>
      <option value="auto">Auto-detect link</option>
      <option value="douyin_favorites">My Douyin favorites</option>
      <option value="douyin_account_liked">Douyin account liked works</option>
    </select>
    <p><label for="input_text">Links or task input</label></p>
    <textarea id="input_text" name="input_text"></textarea>
    <p><button type="submit">Start job</button></p>
  </form>
  <h2>Recent jobs</h2>
  <table>
    <thead><tr><th>ID</th><th>Kind</th><th>Status</th><th>Latest log</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</main>
<script>
document.getElementById("job-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/downloads/api/jobs", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      kind: document.getElementById("kind").value,
      input_text: document.getElementById("input_text").value
    })
  });
  if (response.ok) {
    window.location.reload();
  } else {
    alert("Job submission failed");
  }
});
</script>
</body>
</html>
"""


def create_panel_app(volume_root: Path | str = "Volume") -> FastAPI:
    root = Path(volume_root)
    root.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Private Download Panel")
    store = _job_store(root)
    app.state.job_store = store
    app.state.volume_root = root

    @app.get("/downloads/api/health")
    async def health():
        return {"ok": True, "service": "private-download-panel"}

    @app.get("/downloads/", response_class=HTMLResponse)
    async def index(user: PanelUser = Depends(require_panel_user)):
        return HTMLResponse(_panel_html(user, store.list_jobs()))

    @app.get("/downloads/api/jobs")
    async def list_jobs(user: PanelUser = Depends(require_panel_user)):
        return store.list_jobs()

    @app.post("/downloads/api/jobs")
    async def create_job(
        payload: JobCreate,
        user: PanelUser = Depends(require_panel_user),
    ):
        return store.create_job(payload.kind, payload.input_text)

    @app.get("/downloads/api/jobs/{job_id}")
    async def get_job(job_id: str, user: PanelUser = Depends(require_panel_user)):
        try:
            return store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None

    @app.get("/downloads/api/jobs/{job_id}/files")
    async def get_job_files(job_id: str, user: PanelUser = Depends(require_panel_user)):
        try:
            job = store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None
        return list_files(root, job.output_dir) if job.output_dir else []

    @app.get("/downloads/api/jobs/{job_id}/files/{file_path:path}")
    async def download_job_file(
        job_id: str,
        file_path: str,
        user: PanelUser = Depends(require_panel_user),
    ):
        try:
            job = store.get_job(job_id)
            resolved = resolve_job_file(root, job.output_dir, file_path)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found") from None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file path") from None
        return FileResponse(resolved)

    return app
```

- [ ] **Step 4: Run app tests to verify they pass**

Run:

```powershell
python -m unittest src.private_panel.tests.test_app -v
```

Expected: PASS, all tests in `PrivatePanelAppTests`.

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/private_panel/app.py src/private_panel/tests/test_app.py
git commit -m "feat: add private panel app routes"
```

### Task 6: Panel Launch Mode

**Files:**
- Modify: `main.py`
- Test: `src/private_panel/tests/test_main_panel_mode.py`

- [ ] **Step 1: Write failing launch mode tests**

Create `src/private_panel/tests/test_main_panel_mode.py`:

```python
import unittest
from unittest.mock import patch

import main


class MainPanelModeTests(unittest.TestCase):
    def test_should_run_panel_mode_reads_environment(self):
        with patch.dict("os.environ", {"DOUK_PANEL_MODE": "1"}, clear=False):
            self.assertTrue(main.should_run_panel_mode())

        with patch.dict("os.environ", {"DOUK_PANEL_MODE": "true"}, clear=False):
            self.assertTrue(main.should_run_panel_mode())

        with patch.dict("os.environ", {"DOUK_PANEL_MODE": "0"}, clear=False):
            self.assertFalse(main.should_run_panel_mode())

    def test_panel_host_and_port_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(main.panel_host(), "0.0.0.0")
            self.assertEqual(main.panel_port(), 5555)

    def test_panel_port_reads_environment(self):
        with patch.dict("os.environ", {"DOUK_PANEL_PORT": "7777"}, clear=False):
            self.assertEqual(main.panel_port(), 7777)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run launch tests to verify they fail**

Run:

```powershell
python -m unittest src.private_panel.tests.test_main_panel_mode -v
```

Expected: FAIL with `AttributeError: module 'main' has no attribute 'should_run_panel_mode'`.

- [ ] **Step 3: Modify `main.py` to support panel mode**

Replace `main.py` with:

```python
import os
from asyncio import CancelledError
from asyncio import run

from uvicorn import Config, Server

from src.application import TikTokDownloader
from src.private_panel.app import create_panel_app


def should_run_panel_mode() -> bool:
    return os.environ.get("DOUK_PANEL_MODE", "").lower() in {"1", "true", "yes"}


def panel_host() -> str:
    return os.environ.get("DOUK_PANEL_HOST", "0.0.0.0")


def panel_port() -> int:
    return int(os.environ.get("DOUK_PANEL_PORT", "5555"))


async def run_panel() -> None:
    app = create_panel_app(os.environ.get("DOUK_PANEL_VOLUME", "Volume"))
    config = Config(app, host=panel_host(), port=panel_port(), log_level="info")
    server = Server(config)
    await server.serve()


async def main():
    if should_run_panel_mode():
        await run_panel()
        return

    async with TikTokDownloader() as downloader:
        try:
            await downloader.run()
        except (
            KeyboardInterrupt,
            CancelledError,
        ):
            return


if __name__ == "__main__":
    run(main())
```

- [ ] **Step 4: Run launch tests and a smoke import**

Run:

```powershell
python -m unittest src.private_panel.tests.test_main_panel_mode -v
python -c "import main; print(main.should_run_panel_mode())"
```

Expected: tests PASS; import command prints `False` when `DOUK_PANEL_MODE` is not set.

- [ ] **Step 5: Run all private panel tests**

Run:

```powershell
python -m unittest discover -s src/private_panel/tests -v
```

Expected: PASS for all private panel tests.

- [ ] **Step 6: Commit Task 6**

```powershell
git add main.py src/private_panel/tests/test_main_panel_mode.py
git commit -m "feat: add private panel launch mode"
```

### Task 7: Deployment Artifacts And Regression Check

**Files:**
- Create: `deploy/private-panel/docker-compose.yml`
- Create: `deploy/private-panel/env.example`
- Create: `deploy/private-panel/README.md`
- Test: `src/private_panel/tests/test_deploy_private_panel.py`

- [ ] **Step 1: Write failing deployment artifact tests**

Create `src/private_panel/tests/test_deploy_private_panel.py`:

```python
import unittest
from pathlib import Path


class PrivatePanelDeployArtifactsTests(unittest.TestCase):
    def test_compose_uses_internal_network_without_public_ports(self):
        compose = Path("deploy/private-panel/docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("DOUK_PANEL_MODE=1", compose)
        self.assertIn("oceverse_halo_network", compose)
        self.assertIn("expose:", compose)
        self.assertNotIn("ports:", compose)

    def test_env_example_names_private_token_without_secret_value(self):
        env_text = Path("deploy/private-panel/env.example").read_text(encoding="utf-8")

        self.assertIn("DOUK_PRIVATE_TOKEN=", env_text)
        self.assertNotIn("secret", env_text.lower())
        self.assertIn("DOUK_PANEL_VOLUME=/app/Volume", env_text)

    def test_readme_documents_navi_gated_caddy_route(self):
        readme = Path("deploy/private-panel/README.md").read_text(encoding="utf-8")

        self.assertIn("/downloads", readme)
        self.assertIn("forward_auth", readme)
        self.assertIn("navi-save:8099", readme)
        self.assertIn("Do not publish a host port", readme)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run deployment tests to verify they fail**

Run:

```powershell
python -m unittest src.private_panel.tests.test_deploy_private_panel -v
```

Expected: FAIL with `FileNotFoundError` for `deploy/private-panel/docker-compose.yml`.

- [ ] **Step 3: Add Compose, env example, and README**

Create `deploy/private-panel/docker-compose.yml`:

```yaml
services:
  douk-private-panel:
    build:
      context: ../..
      dockerfile: Dockerfile
    image: douk-private-panel:latest
    container_name: douk-private-panel
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - DOUK_PANEL_MODE=1
      - DOUK_PANEL_HOST=0.0.0.0
      - DOUK_PANEL_PORT=5555
      - DOUK_PANEL_VOLUME=/app/Volume
    expose:
      - "5555"
    volumes:
      - douk_private_panel_volume:/app/Volume
    networks:
      - halo_network

volumes:
  douk_private_panel_volume:

networks:
  halo_network:
    name: oceverse_halo_network
    external: true
```

Create `deploy/private-panel/env.example`:

```dotenv
DOUK_PRIVATE_TOKEN=
DOUK_PANEL_VOLUME=/app/Volume
```

Create `deploy/private-panel/README.md`:

```markdown
# Private Download Panel Deployment

This deployment runs the personal DouK-Downloader panel as an internal Docker service behind the existing navi-gated Caddy gateway.

Do not publish a host port for this service. Browser access should go through `/downloads` after Caddy `forward_auth` verifies the existing `navi_session` cookie through `navi-save:8099`.

## Files

- `docker-compose.yml`: builds and runs the internal panel service.
- `env.example`: copy to `.env` and set `DOUK_PRIVATE_TOKEN` for script/API access.

## Caddy Route Shape

Add `/downloads` and `/downloads/*` to a navi-gated matcher, strip inbound identity headers, run `forward_auth`, then proxy to the internal service:

```caddy
@downloads_gated {
    path /downloads /downloads/*
}
request_header @downloads_gated -X-Tradedocs-User-Id
request_header @downloads_gated -X-Tradedocs-User-Email
request_header @downloads_gated -X-Tradedocs-User-Name

forward_auth @downloads_gated navi-save:8099 {
    uri /navi/verify
    copy_headers X-Tradedocs-User-Id X-Tradedocs-User-Email X-Tradedocs-User-Name
}

handle /downloads {
    reverse_proxy douk-private-panel:5555
}
handle /downloads/* {
    reverse_proxy douk-private-panel:5555
}
```

## First Validation

1. Copy `env.example` to `.env` and set a long random `DOUK_PRIVATE_TOKEN`.
2. Start the service with `docker compose up -d --build`.
3. Confirm the service has no host `ports` entry.
4. Open `/downloads/` while logged out and confirm navi redirects to `/navi/login`.
5. Log in through navi and confirm `/downloads/` renders the panel.
6. Submit a single Douyin link only after the mounted `Volume/settings.json` has the required Cookie settings.
```

- [ ] **Step 4: Run deployment tests to verify they pass**

Run:

```powershell
python -m unittest src.private_panel.tests.test_deploy_private_panel -v
```

Expected: PASS, all tests in `PrivatePanelDeployArtifactsTests`.

- [ ] **Step 5: Run full regression for the slice**

Run:

```powershell
python -m unittest discover -s src/private_panel/tests -v
python -m unittest automation.tests.test_prepare_douyin_sync -v
```

Expected: PASS for private panel tests and existing automation tests.

- [ ] **Step 6: Commit Task 7**

```powershell
git add deploy/private-panel src/private_panel/tests/test_deploy_private_panel.py
git commit -m "docs: add private panel deployment artifacts"
```

## Final Verification Before PR

Run:

```powershell
git status --short --branch
python -m unittest discover -s src/private_panel/tests -v
python -m unittest automation.tests.test_prepare_douyin_sync -v
```

Expected:

- Branch contains only intentional private panel and deployment changes.
- All private panel tests pass.
- Existing Douyin favorites automation tests pass.
- No Cookie, token, downloaded media, `Volume`, or `.env` files are staged.

## Manual Local Smoke Test

Run:

```powershell
$env:DOUK_PANEL_MODE='1'
$env:DOUK_PRIVATE_TOKEN='local-test-token'
python main.py
```

In another shell:

```powershell
curl.exe -H "Authorization: Bearer local-test-token" http://127.0.0.1:5555/downloads/api/health
curl.exe -H "Authorization: Bearer local-test-token" http://127.0.0.1:5555/downloads/api/jobs
```

Expected:

- Health returns `{"ok":true,"service":"private-download-panel"}`.
- Jobs returns `[]` on a fresh local volume.

Stop the local server with Ctrl+C after the smoke test.

## PR Notes

The PR description should state:

- Adds a private navi-gated download panel foundation.
- Keeps the existing CLI and Web API modes intact.
- Adds token auth only for script/API access.
- Does not deploy to the VPS.
- Does not add real Cookie values or media files.
- First real executor path is Douyin single-link jobs; account, favorites, liked, and mix jobs are follow-up slices.
