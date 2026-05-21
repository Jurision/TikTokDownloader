from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VOLUME = PROJECT_ROOT / "Volume"
DEFAULT_RUN_COMMAND = "3 9 Q"
DEFAULT_FOLDER_NAME = "DouyinFavorites"
DEFAULT_TASK_NAME = "DouyinFavoritesWeeklySync"
DEFAULT_CONFIG = PROJECT_ROOT / "automation" / "douyin_favorites_sync.local.json"
SESSION_KEYS = ("sessionid_ss", "sessionid")


def default_output_root() -> str:
    return str(Path.home() / "Downloads" / DEFAULT_FOLDER_NAME)


def expand_path(value: str) -> str:
    expanded = os.path.expandvars(str(value).strip())
    return str(Path(expanded).expanduser()) if expanded.startswith("~") else expanded


def default_sync_config() -> dict[str, Any]:
    return {
        "output_root": default_output_root(),
        "folder_name": DEFAULT_FOLDER_NAME,
        "owner_url": "",
        "browser": "Chrome",
        "run_command": DEFAULT_RUN_COMMAND,
        "task_name": DEFAULT_TASK_NAME,
        "day_of_week": "Sunday",
        "at": "03:30",
        "skip_cookie_refresh": False,
        "allow_missing_owner": False,
        "allow_missing_cookie": False,
    }


def load_sync_config(config_path: Path | None = DEFAULT_CONFIG) -> dict[str, Any]:
    config = default_sync_config()
    if config_path and config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if not isinstance(loaded, dict):
            raise ValueError(f"sync config must be a JSON object: {config_path}")
        config.update({key: value for key, value in loaded.items() if value is not None})
    config["output_root"] = expand_path(config["output_root"])
    return config


def default_settings() -> dict[str, Any]:
    return {
        "accounts_urls": [
            {
                "mark": "",
                "url": "",
                "tab": "",
                "earliest": "",
                "latest": "",
                "enable": True,
            }
        ],
        "accounts_urls_tiktok": [
            {
                "mark": "",
                "url": "",
                "tab": "",
                "earliest": "",
                "latest": "",
                "enable": True,
            }
        ],
        "mix_urls": [{"mark": "", "url": "", "enable": True}],
        "mix_urls_tiktok": [{"mark": "", "url": "", "enable": True}],
        "owner_url": {"mark": "", "url": "", "uid": "", "sec_uid": "", "nickname": ""},
        "owner_url_tiktok": None,
        "root": "",
        "folder_name": "Download",
        "name_format": "create_time type nickname desc",
        "desc_length": 64,
        "name_length": 128,
        "date_format": "%Y-%m-%d %H:%M:%S",
        "split": "-",
        "folder_mode": False,
        "music": False,
        "truncate": 50,
        "storage_format": "",
        "cookie": "",
        "cookie_tiktok": "",
        "dynamic_cover": False,
        "static_cover": False,
        "proxy": "",
        "proxy_tiktok": "",
        "twc_tiktok": "",
        "download": True,
        "max_size": 0,
        "chunk": 1024 * 1024 * 2,
        "timeout": 10,
        "max_retry": 5,
        "max_pages": 0,
        "run_command": "",
        "ffmpeg": "",
        "live_qualities": "",
        "douyin_platform": True,
        "tiktok_platform": True,
        "browser_info": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "pc_libra_divert": "Windows",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "139.0.0.0",
            "engine_name": "Blink",
            "engine_version": "139.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "webid": "",
        },
        "browser_info_tiktok": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "app_language": "zh-Hans",
            "browser_language": "zh-CN",
            "browser_name": "Mozilla",
            "browser_platform": "Win32",
            "browser_version": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "language": "zh-Hans",
            "os": "windows",
            "priority_region": "US",
            "region": "US",
            "tz_name": "Asia/Shanghai",
            "webcast_language": "zh-Hans",
            "device_id": "",
        },
    }


def load_or_create_settings(volume: Path | None = DEFAULT_VOLUME) -> dict[str, Any]:
    settings = default_settings()
    if volume is None:
        return settings

    settings_path = volume / "settings.json"
    if settings_path.exists():
        loaded = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        settings.update(loaded)
    return settings


def save_settings(settings: dict[str, Any], volume: Path) -> None:
    volume.mkdir(parents=True, exist_ok=True)
    settings_path = volume / "settings.json"
    if settings_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = settings_path.with_name(f"settings.json.bak-{stamp}")
        shutil.copy2(settings_path, backup)
    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def apply_sync_settings(
    settings: dict[str, Any],
    output_root: str | None = None,
    owner_url: str = "",
    run_command: str = DEFAULT_RUN_COMMAND,
    folder_name: str = DEFAULT_FOLDER_NAME,
) -> bool:
    before = json.dumps(settings, sort_keys=True, ensure_ascii=False)
    settings["root"] = output_root or default_output_root()
    settings["folder_name"] = folder_name or DEFAULT_FOLDER_NAME
    settings["download"] = True
    settings["run_command"] = run_command
    settings["douyin_platform"] = True
    settings["tiktok_platform"] = False
    owner = settings.get("owner_url")
    if not isinstance(owner, dict):
        owner = {"mark": "", "url": "", "uid": "", "sec_uid": "", "nickname": ""}
        settings["owner_url"] = owner
    owner.setdefault("mark", "")
    owner.setdefault("uid", "")
    owner.setdefault("sec_uid", "")
    owner.setdefault("nickname", "")
    if owner_url:
        owner["url"] = owner_url
    after = json.dumps(settings, sort_keys=True, ensure_ascii=False)
    return before != after


def validate_owner_url(owner_url: dict[str, Any] | None) -> bool:
    if not owner_url:
        return False
    url = str(owner_url.get("url", "")).strip()
    if not url or url == "账号主页链接":
        return False
    return url.startswith("https://www.douyin.com/user/")


def has_logged_in_cookie(cookie: dict[str, str] | str | None) -> bool:
    if isinstance(cookie, dict):
        return any(cookie.get(key) for key in SESSION_KEYS)
    if isinstance(cookie, str):
        return any(f"{key}=" in cookie for key in SESSION_KEYS)
    return False


def refresh_cookie_from_browser(browser_name: str = "Chrome") -> tuple[dict[str, str], str]:
    try:
        import rookiepy
    except ImportError:
        return {}, "rookiepy is not installed"

    browser_getter = getattr(rookiepy, browser_name.lower(), None)
    if browser_getter is None:
        return {}, f"unsupported browser: {browser_name}"
    try:
        cookies = browser_getter(domains=["douyin.com"])
    except Exception as error:
        return {}, f"browser cookie read failed: {error}"
    result = {
        item["name"]: item["value"]
        for item in cookies
        if item.get("name") and item.get("value")
    }
    return result, "ok" if result else "browser returned no douyin cookies"


def ensure_database_options(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS config_data (
            NAME TEXT PRIMARY KEY,
            VALUE INTEGER NOT NULL CHECK(VALUE IN (0, 1))
            );"""
        )
        db.execute("CREATE TABLE IF NOT EXISTS download_data (ID TEXT PRIMARY KEY);")
        db.execute(
            """CREATE TABLE IF NOT EXISTS mapping_data (
            ID TEXT PRIMARY KEY,
            NAME TEXT NOT NULL,
            MARK TEXT NOT NULL
            );"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS option_data (
            NAME TEXT PRIMARY KEY,
            VALUE TEXT NOT NULL
            );"""
        )
        db.executemany(
            "REPLACE INTO config_data (NAME, VALUE) VALUES (?, ?)",
            (("Record", 1), ("Logger", 1), ("Disclaimer", 1)),
        )
        db.execute(
            "REPLACE INTO option_data (NAME, VALUE) VALUES (?, ?)",
            ("Language", "zh_CN"),
        )
        db.commit()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="")
    parser.add_argument("--volume", default=str(DEFAULT_VOLUME))
    parser.add_argument("--output-root", default="")
    parser.add_argument("--folder-name", default="")
    parser.add_argument("--owner-url", default="")
    parser.add_argument("--run-command", default="")
    parser.add_argument("--browser", default="")
    parser.add_argument("--skip-cookie-refresh", action="store_true", default=None)
    parser.add_argument("--allow-missing-owner", action="store_true", default=None)
    parser.add_argument("--allow-missing-cookie", action="store_true", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG
    config = load_sync_config(config_path)
    output_root = expand_path(args.output_root) if args.output_root else config["output_root"]
    folder_name = args.folder_name or config["folder_name"]
    owner_url = args.owner_url or config["owner_url"]
    run_command = args.run_command or config["run_command"]
    browser = args.browser or config["browser"]
    skip_cookie_refresh = (
        args.skip_cookie_refresh
        if args.skip_cookie_refresh is not None
        else bool(config["skip_cookie_refresh"])
    )
    allow_missing_owner = (
        args.allow_missing_owner
        if args.allow_missing_owner is not None
        else bool(config["allow_missing_owner"])
    )
    allow_missing_cookie = (
        args.allow_missing_cookie
        if args.allow_missing_cookie is not None
        else bool(config["allow_missing_cookie"])
    )

    volume = Path(args.volume)
    settings = load_or_create_settings(volume)
    apply_sync_settings(settings, output_root, owner_url, run_command, folder_name)

    cookie_status = "skipped"
    if not skip_cookie_refresh:
        cookie, cookie_status = refresh_cookie_from_browser(browser)
        if cookie:
            settings["cookie"] = cookie

    owner_ok = validate_owner_url(settings.get("owner_url"))
    cookie_ok = has_logged_in_cookie(settings.get("cookie"))
    save_settings(settings, volume)
    ensure_database_options(volume / "DouK-Downloader.db")

    status = {
        "config": str(config_path) if config_path.exists() else "",
        "settings": str(volume / "settings.json"),
        "database": str(volume / "DouK-Downloader.db"),
        "output_root": settings["root"],
        "folder_name": settings["folder_name"],
        "run_command": settings["run_command"],
        "browser": browser,
        "owner_url_configured": owner_ok,
        "cookie_logged_in": cookie_ok,
        "cookie_refresh": cookie_status,
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))

    if not owner_ok and not allow_missing_owner:
        print(
            "owner_url.url is required for Douyin favorited works sync. "
            "Rerun with -OwnerUrl 'https://www.douyin.com/user/...'.",
            file=sys.stderr,
        )
        return 20
    if not cookie_ok and not allow_missing_cookie:
        print(
            "A logged-in Douyin cookie was not found. Open Douyin in Chrome and log in, "
            "then rerun the sync.",
            file=sys.stderr,
        )
        return 21
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
