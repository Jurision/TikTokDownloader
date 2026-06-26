# Douyin Favorites Weekly Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fork-source-first weekly sync that downloads the logged-in Douyin account's favorited works to a release-user-configurable folder.

**Architecture:** A Python helper prepares `Volume/settings.json`, loads a local JSON config, refreshes Douyin cookies from Chrome when possible, and initializes the local SQLite config. A PowerShell sync script discovers Python 3.12, bootstraps the venv, calls the helper, runs `main.py`, and logs output. Setup and scheduled-task scripts create a user-local config and register weekly sync without committing machine-specific paths.

**Tech Stack:** Python 3.12, stdlib `json/sqlite3/unittest`, optional `rookiepy`, PowerShell ScheduledTasks, existing DouK-Downloader source.

---

### Task 1: Prepare Helper Tests

**Files:**
- Create: `D:\APP\TikTokDownloader-src\automation\tests\test_prepare_douyin_sync.py`
- Create later: `D:\APP\TikTokDownloader-src\automation\prepare_douyin_sync.py`

- [ ] **Step 1: Write failing tests**

Create unittest coverage for default settings merge, owner URL validation, run command setup, SQLite initialization, local JSON config loading, environment-variable expansion, and release-friendly default output paths.

- [ ] **Step 2: Run tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m unittest automation.tests.test_prepare_douyin_sync -v`

Expected: import failure because `automation.prepare_douyin_sync` does not exist.

- [ ] **Step 3: Implement helper**

Create `automation\prepare_douyin_sync.py` with pure functions for settings loading, backup, update, cookie validation, optional browser cookie refresh, and SQLite config initialization.

- [ ] **Step 4: Run tests to verify pass**

Run the same unittest command. Expected: all tests pass.

### Task 2: Configurable Source Sync Script

**Files:**
- Modify: `D:\APP\TikTokDownloader-src\automation\sync_douyin_favorites.ps1`
- Create: `D:\APP\TikTokDownloader-src\automation\douyin_favorites_sync.example.json`

- [ ] **Step 1: Implement configurable sync orchestration**

Load `automation\douyin_favorites_sync.local.json` when present, allow command-line overrides, create output/log directories, discover Python 3.12 through `py -3.12` or `python`, create `.venv`, install `requirements.txt` plus `rookiepy`, run `prepare_douyin_sync.py`, then run `main.py` with output captured to timestamped logs.

- [ ] **Step 2: Verify config-only path**

Run: `.\automation\sync_douyin_favorites.ps1 -ConfigOnly -SkipCookieRefresh`

Expected: directories exist under the configured or default Downloads path, settings JSON is valid, and missing `owner_url.url` is reported clearly if not configured.

### Task 3: Setup Script And Weekly Task Installer

**Files:**
- Create: `D:\APP\TikTokDownloader-src\automation\setup_douyin_favorites_sync.ps1`
- Modify: `D:\APP\TikTokDownloader-src\automation\install_weekly_task.ps1`
- Modify: `D:\APP\TikTokDownloader-src\.gitignore`

- [ ] **Step 1: Implement setup and installer**

Generate ignored `automation\douyin_favorites_sync.local.json` from prompts or parameters, then register or replace the configured scheduled task using PowerShell `Register-ScheduledTask`, pointing to `sync_douyin_favorites.ps1`.

- [ ] **Step 2: Verify task registration**

Run installer, then query `Get-ScheduledTask -TaskName DouyinFavoritesWeeklySync`.

Expected: the task exists and points to the sync script.

### Task 4: Manual Verification

**Files:**
- No new files.

- [ ] **Step 1: Validate Python environment**

Run source import checks from `.venv`.

- [ ] **Step 2: Run config-only sync**

Confirm settings and logs.

- [ ] **Step 3: Confirm release hygiene**

Run `git status --short` and confirm no `.venv`, `Volume`, generated local config, logs, cookies, or downloaded media are staged.

- [ ] **Step 4: Run real sync when owner URL and cookie are available**

Run sync without `-ConfigOnly`. Expected: downloader enters favorite works mode and writes activity to logs.
