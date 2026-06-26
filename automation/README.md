# Douyin Favorites Weekly Sync

This automation downloads the logged-in Douyin account's favorited works and can register a weekly Windows scheduled task.

## Quick Start

Run PowerShell from the project root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\automation\setup_douyin_favorites_sync.ps1"
```

The setup script creates `automation\douyin_favorites_sync.local.json`, which is intentionally ignored by git because it contains local paths and your Douyin homepage URL.

## Configuration

Copy `automation\douyin_favorites_sync.example.json` to `automation\douyin_favorites_sync.local.json` or let the setup script generate it.

Important fields:

- `output_root`: download and log root. Supports `%USERPROFILE%` and `~`.
- `owner_url`: your real Douyin homepage URL, such as `https://www.douyin.com/user/...`.
- `browser`: browser used for cookie refresh. Default: `Chrome`.
- `day_of_week` and `at`: weekly scheduled-task time.

## Manual Sync

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\automation\sync_douyin_favorites.ps1"
```

Logs are written to `<output_root>\Logs`.

For Chrome v130 and newer, cookie refresh may require running the scheduled task with highest privileges. Run setup or `install_weekly_task.ps1` from an Administrator PowerShell window to enable that.
