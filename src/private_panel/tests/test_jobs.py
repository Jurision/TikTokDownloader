import threading
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

    def test_claim_next_queued_job_does_not_double_claim_across_stores(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            path = Path(temp) / "jobs.db"
            store = JobStore(path)
            created = store.create_job(JobKind.DOUYIN_SINGLE, "one")
            barrier = threading.Barrier(3)
            lock = threading.Lock()
            results = []
            errors = []

            def claim_in_thread():
                try:
                    barrier.wait(timeout=5)
                    claimed = JobStore(path).claim_next_queued()
                    with lock:
                        results.append(claimed)
                except BaseException as exc:
                    with lock:
                        errors.append(exc)

            threads = [
                threading.Thread(target=claim_in_thread),
                threading.Thread(target=claim_in_thread),
            ]
            for thread in threads:
                thread.start()
            barrier.wait(timeout=5)
            for thread in threads:
                thread.join(timeout=5)

            loaded = store.get_job(created.id)

        self.assertFalse([thread for thread in threads if thread.is_alive()])
        if errors:
            self.fail(f"claim worker failed: {errors!r}")
        self.assertEqual(len(results), 2)
        claims = [claim for claim in results if claim is not None]
        self.assertEqual([claim.id for claim in claims], [created.id])
        self.assertEqual(sum(claim is None for claim in results), 1)
        self.assertEqual(loaded.status, JobStatus.RUNNING)

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

    def test_update_progress_sets_counts_and_log_tail(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")
            created = store.create_job(JobKind.DOUYIN_SINGLE, "one")

            store.update_progress(
                created.id,
                progress_done=2,
                progress_total=5,
                log_tail="two done",
            )
            loaded = store.get_job(created.id)

        self.assertEqual(loaded.progress_done, 2)
        self.assertEqual(loaded.progress_total, 5)
        self.assertEqual(loaded.log_tail, "two done")

    def test_missing_job_raises_key_error(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")

            with self.assertRaises(KeyError):
                store.get_job("missing")

    def test_mark_succeeded_missing_job_raises_key_error(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")

            with self.assertRaises(KeyError):
                store.mark_succeeded("missing", output_dir="jobs/missing")

    def test_mark_failed_missing_job_raises_key_error(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")

            with self.assertRaises(KeyError):
                store.mark_failed("missing", "not found")

    def test_update_progress_missing_job_raises_key_error(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            store = JobStore(Path(temp) / "jobs.db")

            with self.assertRaises(KeyError):
                store.update_progress("missing", progress_done=1, progress_total=2)


if __name__ == "__main__":
    unittest.main()
