import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.private_panel.executor import (
    JobExecutionResult,
    PrivatePanelExecutor,
    _ensure_downloaded_files,
)
from src.private_panel.jobs import JobStore
from src.private_panel.models import JobKind, JobStatus
from src.private_panel.worker import run_one_job, worker_loop


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


class TransientFailingStore:
    def __init__(self):
        self.calls = 0

    def claim_next_queued(self):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("database is locked")
        raise KeyboardInterrupt()


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

    async def test_douyin_single_adapter_wires_core_download_flow(self):
        calls = {}

        class FakeTikTokDownloader:
            def __init__(self):
                self.config = {}
                self.parameter = SimpleNamespace(root=None, folder_name="", download=False)
                self.database = object()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            def check_config(self):
                calls["record_config"] = self.config["Record"]

            async def check_settings(self, interactive):
                calls["check_settings_interactive"] = interactive

        class FakeRecordContext:
            def __init__(self, root, console=None, **params):
                self.root = root
                self.console = console
                self.params = params

            async def __aenter__(self):
                calls["record_context"] = (self.root, self.console, self.params)
                return object()

            async def __aexit__(self, exc_type, exc, traceback):
                return False

        class FakeRecord:
            def run(self, parameter):
                calls["record_parameter"] = parameter
                return parameter.root, {"kind": "detail"}, FakeRecordContext

        class FakeLinks:
            async def run(self, text):
                calls["input_text"] = text
                return ["12345"]

        class FakeTikTok:
            def __init__(self, parameter, database):
                self.parameter = parameter
                self.database = database
                self.console = "console"
                self.record = FakeRecord()
                self.links = FakeLinks()

            async def _handle_detail(self, ids, flag, record):
                calls["detail"] = (ids, flag, record)
                download_dir = self.parameter.root / "Download"
                download_dir.mkdir(parents=True)
                (download_dir / "video.mp4").write_bytes(b"video")

        fake_application = types.ModuleType("src.application")
        fake_application.__path__ = []
        fake_application.TikTokDownloader = FakeTikTokDownloader
        fake_main_terminal = types.ModuleType("src.application.main_terminal")
        fake_main_terminal.TikTok = FakeTikTok

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "https://v.douyin.com/abc/")
            job = store.claim_next_queued()
            modules = {
                "src.application": fake_application,
                "src.application.main_terminal": fake_main_terminal,
            }
            with patch.dict(sys.modules, modules):
                result = await PrivatePanelExecutor(Path(temp)).download_douyin_single(job)

        expected_root = Path(temp) / "private_panel" / "jobs" / created.id / "files"
        self.assertEqual(calls["record_config"], 0)
        self.assertFalse(calls["check_settings_interactive"])
        self.assertEqual(calls["record_parameter"].root, expected_root)
        self.assertEqual(calls["record_parameter"].folder_name, "Download")
        self.assertTrue(calls["record_parameter"].download)
        self.assertEqual(calls["input_text"], "https://v.douyin.com/abc/")
        self.assertEqual(calls["detail"][0], ["12345"])
        self.assertFalse(calls["detail"][1])
        self.assertEqual(result.output_dir, f"private_panel/jobs/{created.id}/files")
        self.assertEqual(result.log_tail, "Downloaded 1 Douyin work item(s)")

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

    async def test_worker_loop_continues_after_transient_store_error(self):
        store = TransientFailingStore()

        with self.assertRaises(KeyboardInterrupt):
            await worker_loop(store, RecordingExecutor(), poll_seconds=0)

        self.assertEqual(store.calls, 2)


if __name__ == "__main__":
    unittest.main()
