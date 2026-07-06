import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.private_panel.app import create_panel_app
from src.private_panel.models import JobStatus


class PrivatePanelAppTests(unittest.TestCase):
    @staticmethod
    def _create_job(client: TestClient) -> dict:
        return client.post(
            "/downloads/api/jobs",
            headers={"X-Tradedocs-User-Id": "user-123"},
            json={"kind": "douyin_single", "input_text": "https://v.douyin.com/abc/"},
        ).json()

    @staticmethod
    def _valid_output_dir(job_id: str) -> str:
        return f"private_panel/jobs/{job_id}/files"

    def test_health_endpoint_is_public_and_minimal(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            response = client.get("/downloads/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "service": "private-download-panel"})

    def test_default_docs_and_schema_are_not_public(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            responses = [
                client.get("/docs"),
                client.get("/redoc"),
                client.get("/openapi.json"),
            ]

        self.assertEqual([response.status_code for response in responses], [404, 404, 404])

    def test_jobs_api_requires_auth(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            response = client.get("/downloads/api/jobs")

        self.assertEqual(response.status_code, 401)

    def test_submit_job_requires_auth(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            response = client.post(
                "/downloads/api/jobs",
                json={"kind": "douyin_single", "input_text": "https://v.douyin.com/abc/"},
            )

        self.assertEqual(response.status_code, 401)

    def test_non_health_routes_require_auth(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            responses = [
                client.get("/downloads/"),
                client.get("/downloads/api/jobs/missing"),
                client.get("/downloads/api/jobs/missing/files"),
                client.get("/downloads/api/jobs/missing/files/video.mp4"),
            ]

        self.assertEqual([response.status_code for response in responses], [401, 401, 401, 401])

    def test_unauthenticated_trailing_slash_variants_do_not_redirect(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            responses = [
                client.get("/downloads", follow_redirects=False),
                client.get("/downloads/api/jobs/", follow_redirects=False),
                client.get("/downloads/api/jobs/missing/", follow_redirects=False),
            ]

        self.assertEqual([response.status_code for response in responses], [404, 404, 404])

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
            client = TestClient(create_panel_app(root))
            created = self._create_job(client)
            output_dir = self._valid_output_dir(created["id"])
            output_path = root / output_dir
            output_path.mkdir(parents=True)
            (output_path / "video.mp4").write_bytes(b"abc")
            app_store = client.app.state.job_store
            app_store.mark_succeeded(created["id"], output_dir, "done")

            response = client.get(
                f"/downloads/api/jobs/{created['id']}/files",
                headers={"X-Tradedocs-User-Id": "user-123"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["relative_path"], "video.mp4")

    def test_job_files_endpoint_returns_400_for_corrupt_output_dir(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)), raise_server_exceptions=False)
            created = client.post(
                "/downloads/api/jobs",
                headers={"X-Tradedocs-User-Id": "user-123"},
                json={"kind": "douyin_single", "input_text": "https://v.douyin.com/abc/"},
            ).json()
            client.app.state.job_store.mark_succeeded(created["id"], "../outside", "done")

            response = client.get(
                f"/downloads/api/jobs/{created['id']}/files",
                headers={"X-Tradedocs-User-Id": "user-123"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Invalid file path"})

    def test_job_files_endpoint_rejects_same_root_corrupt_output_dirs(self):
        corrupt_output_dirs = ["private_panel", ".", "private_panel/jobs.db"]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))
            responses = []
            for corrupt_output_dir in corrupt_output_dirs:
                created = self._create_job(client)
                client.app.state.job_store.mark_succeeded(
                    created["id"],
                    corrupt_output_dir,
                    "done",
                )

                responses.append(
                    client.get(
                        f"/downloads/api/jobs/{created['id']}/files",
                        headers={"X-Tradedocs-User-Id": "user-123"},
                    )
                )

        self.assertEqual([response.status_code for response in responses], [400, 400, 400])

    def test_get_job_returns_404_for_missing_job_with_auth(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))

            response = client.get(
                "/downloads/api/jobs/missing",
                headers={"X-Tradedocs-User-Id": "user-123"},
            )

        self.assertEqual(response.status_code, 404)

    def test_download_job_file_returns_file_content_for_completed_job(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            client = TestClient(create_panel_app(root))
            created = self._create_job(client)
            output_dir = self._valid_output_dir(created["id"])
            output_path = root / output_dir
            output_path.mkdir(parents=True)
            (output_path / "video.mp4").write_bytes(b"abc")
            client.app.state.job_store.mark_succeeded(created["id"], output_dir, "done")

            response = client.get(
                f"/downloads/api/jobs/{created['id']}/files/video.mp4",
                headers={"X-Tradedocs-User-Id": "user-123"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"abc")

    def test_download_job_file_returns_400_for_traversal_path(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            client = TestClient(create_panel_app(root))
            created = self._create_job(client)
            output_dir = self._valid_output_dir(created["id"])
            output_path = root / output_dir
            output_path.mkdir(parents=True)
            (output_path.parent / "secret.txt").write_text("secret", encoding="utf-8")
            client.app.state.job_store.mark_succeeded(created["id"], output_dir, "done")

            response = client.get(
                f"/downloads/api/jobs/{created['id']}/files/..%5Csecret.txt",
                headers={"X-Tradedocs-User-Id": "user-123"},
            )

        self.assertEqual(response.status_code, 400)

    def test_download_job_file_rejects_same_root_corrupt_output_dirs(self):
        cases = [
            ("private_panel", "jobs.db"),
            (".", "private_panel/jobs.db"),
            ("private_panel/jobs.db", "anything.mp4"),
        ]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))
            responses = []
            for corrupt_output_dir, file_path in cases:
                created = self._create_job(client)
                client.app.state.job_store.mark_succeeded(
                    created["id"],
                    corrupt_output_dir,
                    "done",
                )

                responses.append(
                    client.get(
                        f"/downloads/api/jobs/{created['id']}/files/{file_path}",
                        headers={"X-Tradedocs-User-Id": "user-123"},
                    )
                )

        self.assertEqual([response.status_code for response in responses], [400, 400, 400])

    def test_download_job_file_returns_404_when_job_has_no_output_dir(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            client = TestClient(create_panel_app(root))
            created = self._create_job(client)

            response = client.get(
                f"/downloads/api/jobs/{created['id']}/files/private_panel/jobs.db",
                headers={"X-Tradedocs-User-Id": "user-123"},
            )

        self.assertEqual(response.status_code, 404)

    def test_panel_html_escapes_navi_user_names_and_job_log_tails(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            client = TestClient(create_panel_app(Path(temp)))
            created = self._create_job(client)
            client.app.state.job_store.update_progress(
                created["id"],
                progress_done=1,
                progress_total=2,
                log_tail='<script>alert("x")</script>',
            )

            response = client.get(
                "/downloads/",
                headers={
                    "X-Tradedocs-User-Id": "user-123",
                    "X-Tradedocs-User-Name": "<Owner & Co>",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;Owner &amp; Co&gt;", response.text)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", response.text)
        self.assertNotIn("<Owner & Co>", response.text)
        self.assertNotIn('<script>alert("x")</script>', response.text)


if __name__ == "__main__":
    unittest.main()
