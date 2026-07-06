import tempfile
import unittest
from pathlib import Path

from src.private_panel.files import _is_anchored_path, list_files, resolve_job_file


class PrivatePanelFileTests(unittest.TestCase):
    def test_file_path_validator_detects_cross_platform_anchored_paths(self):
        self.assertTrue(_is_anchored_path("/jobs/abc/video.mp4"))
        self.assertTrue(_is_anchored_path(r"\jobs\abc\video.mp4"))
        self.assertTrue(_is_anchored_path(r"C:\jobs\abc\video.mp4"))
        self.assertFalse(_is_anchored_path("nested/video.mp4"))

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

    def test_list_files_rejects_output_dir_path_traversal(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)

            with self.assertRaises(ValueError):
                list_files(root, "../outside")

    def test_list_files_returns_nested_posix_relative_paths(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            job_dir = root / "jobs" / "abc"
            nested_dir = job_dir / "nested"
            nested_dir.mkdir(parents=True)
            file_path = nested_dir / "video.mp4"
            file_path.write_bytes(b"abc")

            entries = list_files(root, "jobs/abc")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "video.mp4")
        self.assertEqual(entries[0].relative_path, "nested/video.mp4")
        self.assertEqual(entries[0].size, 3)

    def test_list_files_skips_symlink_pointing_outside_job_dir(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            job_dir = root / "jobs" / "abc"
            job_dir.mkdir(parents=True)
            external_file = root / "secret.txt"
            external_file.write_text("secret", encoding="utf-8")
            symlink_path = job_dir / "secret-link.txt"
            try:
                symlink_path.symlink_to(external_file)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

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

    def test_resolve_job_file_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            job_dir = root / "jobs" / "abc"
            job_dir.mkdir(parents=True)
            file_path = job_dir / "video.mp4"
            file_path.write_bytes(b"abc")

            with self.assertRaises(ValueError):
                resolve_job_file(root, "jobs/abc", str(file_path))

    def test_resolve_job_file_rejects_posix_rooted_path(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            (root / "jobs" / "abc").mkdir(parents=True)

            with self.assertRaises(ValueError):
                resolve_job_file(root, "jobs/abc", "/jobs/abc/video.mp4")

    def test_resolve_job_file_rejects_windows_rooted_path(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            (root / "jobs" / "abc").mkdir(parents=True)

            with self.assertRaises(ValueError):
                resolve_job_file(root, "jobs/abc", r"\jobs\abc\video.mp4")

    def test_resolve_job_file_rejects_windows_drive_qualified_path(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            (root / "jobs" / "abc").mkdir(parents=True)

            with self.assertRaises(ValueError):
                resolve_job_file(root, "jobs/abc", r"C:\jobs\abc\video.mp4")

    def test_resolve_job_file_rejects_missing_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = Path(temp)
            (root / "jobs" / "abc").mkdir(parents=True)

            with self.assertRaises(FileNotFoundError):
                resolve_job_file(root, "jobs/abc", "missing.mp4")


if __name__ == "__main__":
    unittest.main()
