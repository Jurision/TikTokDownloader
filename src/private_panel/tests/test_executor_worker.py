import tempfile
import unittest
from pathlib import Path

from src.private_panel.executor import (
    JobExecutionResult,
    PrivatePanelExecutor,
    _ensure_downloaded_files,
)
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


class VerboseFailingExecutor(PrivatePanelExecutor):
    def __init__(self, message):
        super().__init__(volume_root=Path("."))
        self.message = message

    async def download_douyin_single(self, job):
        raise RuntimeError(self.message)


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

    async def test_ensure_downloaded_files_accepts_job_download_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            job_output = Path(temp)
            download_dir = job_output / "Download"
            download_dir.mkdir()
            (download_dir / "video.mp4").write_bytes(b"video")

            _ensure_downloaded_files(job_output)

    async def test_ensure_downloaded_files_rejects_empty_download_dir(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            job_output = Path(temp)
            (job_output / "Download").mkdir()

            with self.assertRaisesRegex(
                RuntimeError,
                "Douyin single-link download produced no files",
            ):
                _ensure_downloaded_files(job_output)

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
        self.assertEqual(loaded.error, "RuntimeError: cookie expired")

    async def test_run_one_job_marks_unsupported_kind_failed(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_FAVORITES, "")
            executor = PrivatePanelExecutor(volume_root=Path(temp))

            processed = await run_one_job(store, executor)
            loaded = store.get_job(created.id)

        self.assertTrue(processed)
        self.assertEqual(loaded.status, JobStatus.FAILED)
        self.assertIn("Unsupported job kind", loaded.error)

    async def test_run_one_job_bounds_exception_string(self):
        message = "download failed\r\n" + ("x" * 5000)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "https://v.douyin.com/abc/")
            executor = VerboseFailingExecutor(message)

            processed = await run_one_job(store, executor)
            loaded = store.get_job(created.id)

        self.assertTrue(processed)
        self.assertEqual(loaded.status, JobStatus.FAILED)
        self.assertTrue(loaded.error.startswith("RuntimeError: download failed  "))
        self.assertLessEqual(len(loaded.error), 4000)
        self.assertTrue(loaded.error.endswith("..."))
        self.assertNotIn("\r", loaded.error)
        self.assertNotIn("\n", loaded.error)
        self.assertEqual(loaded.log_tail, loaded.error)

    async def test_run_one_job_returns_false_when_queue_empty(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")

            processed = await run_one_job(store, RecordingExecutor())

        self.assertFalse(processed)


if __name__ == "__main__":
    unittest.main()
