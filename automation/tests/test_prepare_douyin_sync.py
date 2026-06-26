import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from automation.prepare_douyin_sync import (
    apply_sync_settings,
    default_sync_config,
    ensure_database_options,
    has_logged_in_cookie,
    load_or_create_settings,
    load_sync_config,
    validate_owner_url,
)


class PrepareDouyinSyncTests(unittest.TestCase):
    def test_load_or_create_settings_merges_missing_defaults(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            volume = Path(temp)
            settings_path = volume / "settings.json"
            settings_path.write_text(
                json.dumps({"root": "E:\\Old", "cookie": {"sessionid_ss": "abc"}}),
                encoding="utf-8",
            )

            settings = load_or_create_settings(volume)

            self.assertEqual(settings["root"], "E:\\Old")
            self.assertIn("owner_url", settings)
            self.assertIn("run_command", settings)
            self.assertEqual(settings["cookie"], {"sessionid_ss": "abc"})

    def test_apply_sync_settings_sets_expected_values(self):
        settings = load_or_create_settings(None)

        changed = apply_sync_settings(
            settings,
            output_root="E:\\DouyinFavorites",
            owner_url="https://www.douyin.com/user/MS4wLjABAAAA-test",
            run_command="3 9 Q",
            folder_name="MyFavorites",
        )

        self.assertTrue(changed)
        self.assertEqual(settings["root"], "E:\\DouyinFavorites")
        self.assertEqual(settings["folder_name"], "MyFavorites")
        self.assertEqual(settings["owner_url"]["url"], "https://www.douyin.com/user/MS4wLjABAAAA-test")
        self.assertEqual(settings["run_command"], "3 9 Q")
        self.assertTrue(settings["download"])
        self.assertTrue(settings["douyin_platform"])
        self.assertFalse(settings["tiktok_platform"])

    def test_default_sync_config_uses_user_downloads_folder(self):
        with patch(
            "automation.prepare_douyin_sync.Path.home",
            return_value=Path("C:/Users/Alice"),
        ):
            config = default_sync_config()

        self.assertEqual(
            config["output_root"],
            str(Path("C:/Users/Alice") / "Downloads" / "DouyinFavorites"),
        )
        self.assertNotIn("E:\\", config["output_root"])
        self.assertEqual(config["folder_name"], "DouyinFavorites")
        self.assertEqual(config["run_command"], "3 9 Q")

    def test_load_sync_config_merges_defaults_and_expands_environment(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            config_path = Path(temp) / "douyin_favorites_sync.local.json"
            config_path.write_text(
                json.dumps(
                    {
                        "output_root": "%USERPROFILE%\\Videos\\Douyin",
                        "owner_url": "https://www.douyin.com/user/MS4wLjABAAAA-test",
                        "skip_cookie_refresh": True,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"USERPROFILE": "C:\\Users\\Alice"}):
                config = load_sync_config(config_path)

        self.assertEqual(config["output_root"], "C:\\Users\\Alice\\Videos\\Douyin")
        self.assertEqual(config["browser"], "Chrome")
        self.assertEqual(config["owner_url"], "https://www.douyin.com/user/MS4wLjABAAAA-test")
        self.assertTrue(config["skip_cookie_refresh"])

    def test_load_sync_config_accepts_missing_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            config = load_sync_config(Path(temp) / "missing.json")

        self.assertIn("Downloads", config["output_root"])
        self.assertEqual(config["task_name"], "DouyinFavoritesWeeklySync")

    def test_validate_owner_url_rejects_missing_or_placeholder(self):
        self.assertFalse(validate_owner_url({"url": ""}))
        self.assertFalse(validate_owner_url({"url": "账号主页链接"}))
        self.assertFalse(validate_owner_url({"url": "https://example.com/user/abc"}))
        self.assertTrue(
            validate_owner_url(
                {"url": "https://www.douyin.com/user/MS4wLjABAAAA-test"}
            )
        )

    def test_has_logged_in_cookie_accepts_session_keys(self):
        self.assertTrue(has_logged_in_cookie({"sessionid_ss": "abc"}))
        self.assertTrue(has_logged_in_cookie("foo=bar; sessionid_ss=abc;"))
        self.assertFalse(has_logged_in_cookie({}))
        self.assertFalse(has_logged_in_cookie("foo=bar"))

    def test_ensure_database_options_accepts_disclaimer_and_logger(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            db_path = Path(temp) / "DouK-Downloader.db"

            ensure_database_options(db_path)

            with sqlite3.connect(db_path) as db:
                config = dict(db.execute("SELECT NAME, VALUE FROM config_data").fetchall())
                options = dict(db.execute("SELECT NAME, VALUE FROM option_data").fetchall())

            self.assertEqual(config["Record"], 1)
            self.assertEqual(config["Logger"], 1)
            self.assertEqual(config["Disclaimer"], 1)
            self.assertEqual(options["Language"], "zh_CN")


if __name__ == "__main__":
    unittest.main()
