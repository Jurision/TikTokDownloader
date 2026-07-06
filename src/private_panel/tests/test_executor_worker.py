import asyncio
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
    _ensure_output_files,
)
from src.private_panel.jobs import JobStore
from src.private_panel.models import JobKind, JobRecord, JobStatus
from src.private_panel.worker import run_one_job, worker_loop


class RecordingExecutor(PrivatePanelExecutor):
    def __init__(self):
        super().__init__(volume_root=Path("."))
        self.seen = []

    def _record(self, job, message):
        self.seen.append((job.kind, job.id))
        return JobExecutionResult(
            output_dir=f"jobs/{job.id}",
            log_tail=message,
        )

    async def download_douyin_single(self, job):
        return self._record(job, "downloaded one douyin link")

    async def download_douyin_account_posts(self, job):
        return self._record(job, "downloaded account posts")

    async def download_douyin_account_liked(self, job):
        return self._record(job, "downloaded account liked")

    async def download_douyin_favorites(self, job):
        return self._record(job, "downloaded favorites")

    async def download_douyin_mix(self, job):
        return self._record(job, "downloaded mix")


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
    async def asyncSetUp(self):
        asyncio.get_running_loop().slow_callback_duration = 10

    @staticmethod
    def _job(kind: JobKind, id_: str = "job") -> JobRecord:
        return JobRecord(
            id=id_,
            kind=kind,
            status=JobStatus.RUNNING,
            input_text="https://v.douyin.com/abc/",
            created_at="2026-07-06T00:00:00Z",
        )

    def _patch_core_modules(self, calls, terminal_cls):
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

        fake_application = types.ModuleType("src.application")
        fake_application.__path__ = []
        fake_application.TikTokDownloader = FakeTikTokDownloader
        fake_main_terminal = types.ModuleType("src.application.main_terminal")
        fake_main_terminal.TikTok = terminal_cls
        return patch.dict(
            sys.modules,
            {
                "src.application": fake_application,
                "src.application.main_terminal": fake_main_terminal,
            },
        )

    async def test_executor_dispatches_supported_douyin_kinds(self):
        cases = [
            (JobKind.DOUYIN_SINGLE, "downloaded one douyin link"),
            (JobKind.DOUYIN_ACCOUNT_POSTS, "downloaded account posts"),
            (JobKind.DOUYIN_ACCOUNT_LIKED, "downloaded account liked"),
            (JobKind.DOUYIN_FAVORITES, "downloaded favorites"),
            (JobKind.DOUYIN_MIX, "downloaded mix"),
        ]
        executor = RecordingExecutor()
        for index, (kind, message) in enumerate(cases, start=1):
            job = self._job(kind, f"job-{index}")

            result = await executor.execute(job)

            self.assertEqual(result.output_dir, f"jobs/{job.id}")
            self.assertEqual(result.log_tail, message)
            self.assertEqual(executor.seen[-1], (kind, job.id))

    async def test_executor_rejects_unsupported_kind(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            store.create_job(JobKind.TIKTOK_SINGLE, "")
            job = store.claim_next_queued()
            executor = PrivatePanelExecutor(volume_root=Path(temp))

            with self.assertRaises(NotImplementedError):
                await executor.execute(job)

    async def test_douyin_single_adapter_wires_core_download_flow(self):
        calls = {}

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

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "https://v.douyin.com/abc/")
            job = store.claim_next_queued()
            with self._patch_core_modules(calls, FakeTikTok):
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

    async def test_douyin_account_posts_adapter_wires_account_post_flow(self):
        calls = {}

        class FakeTikTok:
            def __init__(self, parameter, database):
                self.parameter = parameter
                self.database = database
                self.owner = SimpleNamespace(url="https://www.douyin.com/user/me", mark="Me")

            async def check_sec_user_id(self, text, tiktok=False):
                calls["check_user"] = (text, tiktok)
                return "sec-user-123"

            async def deal_account_detail(self, index, sec_user_id, tab="post", **kwargs):
                calls["account"] = (index, sec_user_id, tab, kwargs)
                download_dir = self.parameter.root / "UID_posts"
                download_dir.mkdir(parents=True)
                (download_dir / "video.mp4").write_bytes(b"video")
                return True

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(
                JobKind.DOUYIN_ACCOUNT_POSTS,
                "https://www.douyin.com/user/abc",
            )
            job = store.claim_next_queued()
            with self._patch_core_modules(calls, FakeTikTok):
                result = await PrivatePanelExecutor(Path(temp)).download_douyin_account_posts(job)
            expected_root = Path(temp) / "private_panel" / "jobs" / created.id / "files"
            file_written = (expected_root / "UID_posts" / "video.mp4").is_file()

        self.assertEqual(calls["record_config"], 0)
        self.assertFalse(calls["check_settings_interactive"])
        self.assertEqual(calls["check_user"], ("https://www.douyin.com/user/abc", False))
        self.assertEqual(calls["account"][0:3], (0, "sec-user-123", "post"))
        self.assertEqual(calls["account"][3], {})
        self.assertTrue(file_written)
        self.assertEqual(result.output_dir, f"private_panel/jobs/{created.id}/files")
        self.assertEqual(result.log_tail, "Downloaded Douyin account posts")

    async def test_douyin_account_liked_adapter_uses_owner_url_when_input_is_blank(self):
        calls = {}

        class FakeTikTok:
            def __init__(self, parameter, database):
                self.parameter = parameter
                self.database = database
                self.owner = SimpleNamespace(url="https://www.douyin.com/user/me", mark="Me")

            async def check_sec_user_id(self, text, tiktok=False):
                calls["check_user"] = (text, tiktok)
                return "sec-owner"

            async def deal_account_detail(self, index, sec_user_id, tab="post", **kwargs):
                calls["account"] = (index, sec_user_id, tab, kwargs)
                download_dir = self.parameter.root / "UID_liked"
                download_dir.mkdir(parents=True)
                (download_dir / "liked.mp4").write_bytes(b"video")
                return True

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_ACCOUNT_LIKED, "   ")
            job = store.claim_next_queued()
            with self._patch_core_modules(calls, FakeTikTok):
                result = await PrivatePanelExecutor(Path(temp)).download_douyin_account_liked(job)
            expected_root = Path(temp) / "private_panel" / "jobs" / created.id / "files"
            file_written = (expected_root / "UID_liked" / "liked.mp4").is_file()

        self.assertEqual(calls["check_user"], ("https://www.douyin.com/user/me", False))
        self.assertEqual(calls["account"][0:3], (0, "sec-owner", "favorite"))
        self.assertTrue(file_written)
        self.assertEqual(result.output_dir, f"private_panel/jobs/{created.id}/files")
        self.assertEqual(result.log_tail, "Downloaded Douyin account liked works")

    async def test_douyin_favorites_adapter_wires_collection_flow(self):
        calls = {}

        class FakeTikTok:
            def __init__(self, parameter, database):
                self.parameter = parameter
                self.database = database
                self.owner = SimpleNamespace(url="https://www.douyin.com/user/me", mark="Me")

            async def check_sec_user_id(self, text, tiktok=False):
                calls["check_user"] = (text, tiktok)
                return "sec-owner"

            async def _deal_collection_data(self, sec_user_id, **kwargs):
                calls["collection"] = (sec_user_id, kwargs)
                download_dir = self.parameter.root / "UID_collection"
                download_dir.mkdir(parents=True)
                (download_dir / "favorite.mp4").write_bytes(b"video")
                return True

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_FAVORITES, "")
            job = store.claim_next_queued()
            with self._patch_core_modules(calls, FakeTikTok):
                result = await PrivatePanelExecutor(Path(temp)).download_douyin_favorites(job)
            expected_root = Path(temp) / "private_panel" / "jobs" / created.id / "files"
            file_written = (expected_root / "UID_collection" / "favorite.mp4").is_file()

        self.assertEqual(calls["check_user"], ("https://www.douyin.com/user/me", False))
        self.assertEqual(calls["collection"], ("sec-owner", {}))
        self.assertTrue(file_written)
        self.assertEqual(result.output_dir, f"private_panel/jobs/{created.id}/files")
        self.assertEqual(result.log_tail, "Downloaded logged-in Douyin favorites")

    async def test_douyin_mix_adapter_wires_mix_flow(self):
        calls = {}

        class FakeTikTok:
            def __init__(self, parameter, database):
                self.parameter = parameter
                self.database = database
                self.owner = SimpleNamespace(url="", mark="")

            async def _check_mix_id(self, text, tiktok):
                calls["check_mix"] = (text, tiktok)
                return True, "mix-123", ""

            async def deal_mix_detail(self, mix_id, id_, **kwargs):
                calls["mix"] = (mix_id, id_, kwargs)
                download_dir = self.parameter.root / "MID_mix"
                download_dir.mkdir(parents=True)
                (download_dir / "mix.mp4").write_bytes(b"video")
                return True

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_MIX, "https://www.douyin.com/video/123")
            job = store.claim_next_queued()
            with self._patch_core_modules(calls, FakeTikTok):
                result = await PrivatePanelExecutor(Path(temp)).download_douyin_mix(job)
            expected_root = Path(temp) / "private_panel" / "jobs" / created.id / "files"
            file_written = (expected_root / "MID_mix" / "mix.mp4").is_file()

        self.assertEqual(calls["check_mix"], ("https://www.douyin.com/video/123", False))
        self.assertEqual(calls["mix"], (True, "mix-123", {}))
        self.assertTrue(file_written)
        self.assertEqual(result.output_dir, f"private_panel/jobs/{created.id}/files")
        self.assertEqual(result.log_tail, "Downloaded Douyin mix works")

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

    async def test_ensure_output_files_ignores_data_record_files(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            job_output = Path(temp)
            data_dir = job_output / "Data"
            data_dir.mkdir()
            (data_dir / "record.txt").write_text("metadata", encoding="utf-8")

            with self.assertRaisesRegex(
                RuntimeError,
                "Douyin account posts produced no files",
            ):
                _ensure_output_files(job_output, "Douyin account posts")

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
            created = store.create_job(JobKind.TIKTOK_SINGLE, "")
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
        errors = []

        with self.assertRaises(KeyboardInterrupt):
            await worker_loop(store, RecordingExecutor(), poll_seconds=0, on_error=errors.append)

        self.assertEqual(store.calls, 2)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)


if __name__ == "__main__":
    unittest.main()
