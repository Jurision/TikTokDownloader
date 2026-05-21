# Douyin Favorites Weekly Sync Design

Date: 2026-05-21
Repository: Jurision/TikTokDownloader
Local source path: D:\APP\TikTokDownloader-src
Installed fallback path: D:\APP\TikTokDownloader

## Goal

Download all videos from the logged-in Douyin account's favorited works to a user-configured folder, then keep that folder updated once per week.

The target source is Douyin "收藏作品", not named Douyin collection folders.

## Fork-First Constraint

Prefer the user's GitHub fork, `Jurision/TikTokDownloader`, over the packaged installation.

The local packaged installation at `D:\APP\TikTokDownloader` remains useful as a known working fallback, but new automation should live beside the fork source in `D:\APP\TikTokDownloader-src`. The fork's source is the maintainable source of truth.

The initial `git clone` attempt was interrupted by GitHub connection resets. A source zipball from the fork was downloaded and expanded to `D:\APP\TikTokDownloader-src` for local inspection and scripting. If publishing changes back to GitHub is required, use the GitHub connector or retry a shallow clone later.

## Existing Context

The fork source is a Python 3.12 project named `DouK-Downloader`.

The project requires Python 3.12. Automation must not hard-code a machine-specific Python path. It should prefer an existing project `.venv`, then discover Python through `py -3.12`, then `python`, and fail with a clear install message if Python 3.12 is unavailable.

Important source files:

- `main.py`: async entry point.
- `src/application/TikTokDownloader.py`: top-level application menu and mode dispatch.
- `src/application/main_terminal.py`: terminal-mode feature dispatch, including `collection_interactive` for Douyin favorite works.
- `src/tools/browser.py`: browser cookie reader based on `rookiepy`.
- `src/config/settings.py`: default `Volume/settings.json` schema.
- `src/config/parameter.py`: runtime validation for `run_command`, cookies, root, and folder settings.

The fork's current source has browser-cookie menu entries commented out, while the packaged local V5.7 executable exposes them. The automation should therefore not rely on those menu entries being active. It should refresh cookies through source-level helper code or direct configuration updates.

## Proposed Approach

Add a small automation layer to the fork source:

1. Prepare the source checkout's `Volume/settings.json` for the desired download destination and automatic menu flow.
2. Before each sync, try to refresh the Douyin cookie from the already logged-in local browser session using the existing cookie/browser helper code where practical.
3. Run the source project in terminal mode with `run_command` set to the Douyin favorite works path.
4. Keep logs in the configured output folder.
5. Register a Windows scheduled task that runs the sync script weekly.
6. Provide a setup script and example JSON config so a new release user can configure the feature without editing scripts.

The installed `main.exe` is a fallback only if the source environment cannot run.

## Output

Downloaded videos go under the configured `output_root`. The release-friendly default is the current user's Downloads folder:

`%USERPROFILE%\Downloads\DouyinFavorites`

Favorite works mode stores files in the downloader's account-based folder format under the configured root, such as `UID..._..._收藏作品`. Logs go under `<output_root>\Logs`.

The automation must not delete downloaded videos or reset downloader records.

## Required Douyin Settings

Favorite works mode requires:

- A valid Douyin `cookie` for the logged-in account.
- `owner_url.url` set to that same account's Douyin homepage URL.
- `root` set to the configured `output_root`.
- `download` set to `true`.
- `run_command` set to terminal mode plus favorite works plus quit.

In current fork source, the main menu order makes terminal mode option 3 and favorite works function option 9. The planned run command is:

`3 9 Q`

If the packaged fallback is used, its menu order differs, so fallback scripts must set the packaged run command separately.

## Cookie Handling

The preferred steady state is mostly hands-off:

- Each scheduled run first tries to read the latest Douyin cookie from a local logged-in browser session.
- If Chrome's Douyin session is valid, the scheduled sync proceeds without user action.
- If Douyin requires QR login, CAPTCHA, SMS, or other verification, the script cannot bypass that challenge. It should write a clear log entry and open or point to the Douyin login page so the user can refresh the browser login once.

Known local browser context:

- Chrome profile name: `用户1`
- The Chrome extension backend is available through the generic browser runtime if needed.

Because `rookiepy` may not select Chrome profiles explicitly and the project documentation marks browser-cookie reading as compatibility-sensitive, the design should keep cookie refresh modular:

1. Try project-native browser-cookie extraction.
2. If that fails, keep existing configured cookie and run a validation-oriented sync.
3. If sync output indicates an invalid or missing cookie, surface a clear relogin instruction in the log.

## Scheduled Task

Create a Windows scheduled task named by configuration, defaulting to:

`DouyinFavoritesWeeklySync`

It should run once per week under the current Windows user and execute the source-side sync PowerShell script. The task should write stdout/stderr to log files under `<output_root>\Logs`.

## Configuration Model

Repository-tracked files:

- `automation/douyin_favorites_sync.example.json`: safe example values and documented defaults.
- `automation/setup_douyin_favorites_sync.ps1`: interactive first-run setup for release users.
- `automation/sync_douyin_favorites.ps1`: sync entry point.
- `automation/install_weekly_task.ps1`: scheduled task installer.

User-local file:

- `automation/douyin_favorites_sync.local.json`: generated or copied from the example, ignored by git.

Configuration keys:

- `output_root`: download and log root. Supports `%USERPROFILE%` and `~`.
- `owner_url`: the user's real Douyin homepage URL.
- `browser`: browser name for cookie refresh, default `Chrome`.
- `run_command`: downloader menu automation, default `3 9 Q`.
- `task_name`: Windows scheduled task name.
- `day_of_week`: weekly trigger day.
- `at`: weekly trigger time in `HH:mm`.
- `skip_cookie_refresh`, `allow_missing_owner`, `allow_missing_cookie`: advanced booleans.

## Files To Add

- `D:\APP\TikTokDownloader-src\automation\sync_douyin_favorites.ps1`
- `D:\APP\TikTokDownloader-src\automation\install_weekly_task.ps1`
- `D:\APP\TikTokDownloader-src\automation\setup_douyin_favorites_sync.ps1`
- `D:\APP\TikTokDownloader-src\automation\douyin_favorites_sync.example.json`
- `D:\APP\TikTokDownloader-src\automation\README.md`

Optional follow-up if the source environment is healthy:

- `D:\APP\TikTokDownloader-src\automation\refresh_douyin_cookie.py`

## Error Handling

The sync script should:

- Create output and log directories if missing.
- Backup `Volume/settings.json` before configuration changes.
- Fail early with a clear message if `main.py` or `Volume/settings.json` is missing.
- Capture downloader output in a timestamped log file.
- Return a non-zero exit code when the downloader fails.
- Preserve `Volume/DouK-Downloader.db` and `Volume/Cache/IDRecorder.txt` so deduplication remains intact.

## Testing And Verification

Before installing the scheduled task:

1. Verify the source project can load with Python 3.12 and its dependencies.
2. Verify `Volume/settings.json` is valid JSON after edits.
3. Verify the output and log directories are created.
4. Run a config-check or dry-run path if implemented.
5. Run the sync once manually enough to confirm it reaches favorite works mode.

After installing the scheduled task:

1. Query the scheduled task by name.
2. Start the task manually once.
3. Check the latest log file for cookie refresh and favorite download activity.

## Out Of Scope

- Bypassing Douyin login, QR verification, CAPTCHA, or account security challenges.
- Reimplementing Douyin private APIs.
- Deleting or reorganizing old downloaded files.
- Replacing the user's packaged installation.
