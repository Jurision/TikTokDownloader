# Private Download Panel Design

Date: 2026-07-06
Repository: Jurision/TikTokDownloader
Local source path: D:\APP\TikTokDownloader-src
Target deployment: US_Boston VPS, behind the existing navi-gated Caddy gateway

## Goal

Turn the fork into a personal private web tool for downloading Douyin and TikTok works from the sources the user actually wants to use:

- The logged-in account's Douyin favorited works.
- The logged-in account's Douyin liked works.
- Other creators' homepage/video pages.
- Single video or image-post links.
- Single collection/mix links.

The first version should be useful from a browser: paste a link or pick a personal sync task, submit it, watch progress, and retrieve the downloaded files.

## Non-Goals

This is not a public SaaS product. The first version will not include public registration, user management, billing, shared download links, quota systems, or per-customer cookie isolation.

This is not a rewrite of the existing DouK-Downloader core. The panel should wrap existing parsing and downloading behavior instead of reimplementing Douyin or TikTok private API logic.

This should not replace navi authentication. Navi remains the gate.

## Existing Context

The fork already contains the core capabilities:

- `src/application/main_terminal.py` supports account downloads, link downloads, collection downloads, collection-folder downloads, and mix downloads.
- `src/application/main_server.py` exposes FastAPI endpoints for data acquisition, but those endpoints mostly return extracted data in API mode and are not yet a complete "submit download job and retrieve files" product surface.
- `automation/` already contains a release-friendly Douyin favorites sync flow with config-first local settings and the current source menu path `3 9 Q`.
- `Dockerfile` already builds a Python 3.12 container and stores state under `/app/Volume`.

The Boston VPS already has an HTTP edge:

- `caddy-gateway` is the real public 80/443 gateway.
- `navi-save` is internal-only on the shared Docker network and handles `/navi/verify`.
- Caddy already uses `forward_auth` to gate paths with the `navi_session` cookie.
- Current navi identity propagation uses copied headers named `X-Tradedocs-User-Id`, `X-Tradedocs-User-Email`, and `X-Tradedocs-User-Name`.

## Recommended Approach

Build a lightweight private web panel inside this fork and deploy it under the existing navi gate, for example:

`https://arielzhu.space/downloads/`

The deployed container should not expose a public host port. Caddy should reverse-proxy to the container over the existing Docker network after `forward_auth` passes.

The application should accept authenticated browser traffic from navi-gated Caddy and optional direct API calls protected by a private token. The app should not parse or mint `navi_session` itself.

## Navi Gate Integration

Navi remains the authentication authority.

The Caddy route for `/downloads` should:

1. Include `/downloads` and `/downloads/*` in a navi-gated matcher.
2. Strip any inbound identity headers before auth.
3. Call `forward_auth` against `navi-save:8099` with `uri /navi/verify`.
4. Copy the current navi identity headers into the proxied request.
5. Proxy to the downloader panel container on the internal Docker network.

The downloader panel should trust navi identity only when the request arrives from the configured reverse proxy path. It should also support `DOUK_PRIVATE_TOKEN` for script/API access. Browser UI requests should work through navi without requiring the user to paste a second token.

For the MVP, the app may accept the existing `X-Tradedocs-*` identity headers because they are already emitted by navi. The app should name this dependency clearly as "navi identity headers" internally so a future navi cleanup can add neutral `X-Navi-*` headers without changing the product behavior.

## User Experience

The first screen is the tool itself, not a landing page.

Primary views:

- Submit: paste one or more Douyin/TikTok URLs, choose source type, and start a task.
- Personal Sync: buttons for "my Douyin favorites" and "my Douyin liked works".
- Jobs: list recent jobs with status, source type, submitted time, item count, output size, and latest log line.
- Job Detail: show progress, logs, resolved source IDs, output folder, and files.
- Files: browse files produced by a job and download individual files.

Expected source type options:

- Auto-detect link.
- Douyin account posts.
- Douyin account liked works.
- Douyin single work link.
- Douyin mix/collection link.
- Douyin logged-in favorites.
- TikTok account posts.
- TikTok account liked works.
- TikTok single work link.
- TikTok collection link.

The UI should be compact and operational. It should avoid marketing copy and should be comfortable for repeated use.

## Backend Architecture

Add a private panel layer around existing core functions:

- `src/private_panel/app.py`: FastAPI application factory, route registration, static/template mounting.
- `src/private_panel/auth.py`: navi identity header parsing and private-token checks.
- `src/private_panel/models.py`: Pydantic request/response models and job enums.
- `src/private_panel/jobs.py`: SQLite-backed job store.
- `src/private_panel/worker.py`: single-process async worker that executes queued jobs one at a time.
- `src/private_panel/executor.py`: adapters from panel job types to existing DouK-Downloader core methods.
- `src/private_panel/files.py`: safe file listing and file download helpers rooted under the configured output directory.
- `src/private_panel/templates/`: minimal HTML templates.
- `src/private_panel/static/`: small CSS and JavaScript assets.

Keep the existing terminal and API modes working. Add a separate launch mode for the panel rather than changing the current default interactive behavior.

## Job Model

Use SQLite under `Volume/private_panel/jobs.db`.

Each job should store:

- `id`: opaque short ID.
- `kind`: source type enum.
- `status`: `queued`, `running`, `succeeded`, `failed`, or `cancelled`.
- `input_text`: original submitted link/text, redacted where needed.
- `platform`: `douyin` or `tiktok`.
- `created_at`, `started_at`, `finished_at`.
- `progress_total`, `progress_done`.
- `output_dir`: relative path under the panel output root.
- `log_tail`: recent text summary for the job list.
- `error`: failure reason for display.

Job logs should be written to a per-job log file under `Volume/private_panel/jobs/<job_id>/job.log`.

## Download Execution

The MVP should run one worker at a time. This keeps the tool predictable and lowers the risk of platform throttling or account/IP risk controls.

Execution mapping:

- Single work links should reuse the existing link extraction and detail download flow.
- Account posts and liked works should reuse account acquisition with `tab=post` or `tab=favorite`.
- Mix/collection links should reuse the existing mix handling flow.
- Logged-in Douyin favorites should reuse the same underlying collection behavior as `collection_interactive`, but without a terminal prompt.

The executor should call existing core methods directly where practical. If a core path is too coupled to terminal prompts, introduce a small adapter method in the existing application layer with tests instead of driving text menus.

## Cookie and Settings Handling

The deployed private panel should read persistent settings from `Volume/settings.json` and secrets from mounted files or environment variables.

Required operator-provided settings:

- Douyin `cookie` for logged-in-only functions.
- `owner_url.url` for logged-in Douyin favorites.
- TikTok `cookie_tiktok` and TikTok browser/device settings if TikTok liked/account features need login.
- `root` or panel output root pointing at the mounted download volume.
- Optional proxy settings if TikTok requests need a proxy.

Cookie values must not be committed to git, returned in API responses, or displayed in logs.

Cookie refresh is out of scope for the first deployed VPS version because the server cannot read the user's local browser cookies. Expired cookies should produce a clear "cookie expired or missing" failure message and instructions for updating the mounted configuration.

## File Storage

The container should keep all persistent state in a mounted volume, for example:

- `/app/Volume/settings.json`
- `/app/Volume/private_panel/jobs.db`
- `/app/Volume/private_panel/jobs/<job_id>/job.log`
- `/app/Volume/Downloads/...`

File browsing must be rooted under the configured output directory. The file API must reject path traversal and must not expose arbitrary files from the container.

## Deployment Shape

Add deployment artifacts for the personal tool:

- `deploy/private-panel/docker-compose.yml`
- `deploy/private-panel/README.md`
- `deploy/private-panel/env.example`

The Compose service should:

- Build from this repository or use a locally built image.
- Join the existing Caddy Docker network used by navi.
- Mount a named or host directory volume for `/app/Volume`.
- Set `DOUK_PANEL_MODE=1`.
- Set `DOUK_PRIVATE_TOKEN` for non-browser API calls.
- Avoid publishing a public host port by default.

Caddy should add a route like `/downloads` and `/downloads/*` behind the existing navi `forward_auth` flow.

Deployment to the live VPS still requires an explicit deployment step and validation. The design document does not authorize production changes by itself.

## Security

Security posture for MVP:

- Public access goes through HTTPS and navi.
- The app is reachable only through Caddy on the internal Docker network.
- Direct API calls require `DOUK_PRIVATE_TOKEN`.
- Incoming identity headers are stripped before Caddy performs `forward_auth`.
- Cookie values are never rendered back to the browser.
- Job file downloads are limited to job-owned output paths.
- The worker is single-concurrency by default.

The app should expose a simple `/downloads/api/health` endpoint that does not reveal cookies, paths outside the app, environment variables, or job inputs.

## Error Handling

User-facing failures should be explicit:

- Missing or expired Cookie.
- Invalid link or unsupported source type.
- Empty account/mix result.
- Platform request timeout or rate limit.
- Disk full or output directory unwritable.
- Download failed after configured retries.

Every failed job should retain enough log context for debugging without exposing secrets.

## Testing Strategy

Unit tests:

- Auth accepts navi identity headers and rejects unauthenticated API requests.
- Token auth accepts the configured token and rejects missing or wrong tokens.
- Job store transitions are valid and persist across process restarts.
- File listing rejects path traversal.
- Executor dispatch maps each job kind to the correct core adapter.

Integration tests:

- Start the panel app with a temporary `Volume`.
- Submit a queued job using token auth.
- Verify job status transitions.
- Verify file API only serves files under the temporary output root.

Manual deployment validation:

- Confirm `/downloads/` redirects to `/navi/login` when not logged in.
- Confirm logged-in navi session can open `/downloads/`.
- Confirm the container has no public host port.
- Submit a harmless config-only or dry-run job first.
- Submit one real single-video job.
- Confirm files are written to the mounted volume and visible in the job detail page.

## First Implementation Slice

The first PR should implement:

1. The private panel app shell.
2. Navi/token auth checks.
3. SQLite job store.
4. Single worker skeleton.
5. Single-link Douyin download job.
6. File listing for completed jobs.
7. Docker Compose and Caddy deployment notes.

After that works, add account liked works, logged-in favorites, and mix downloads as follow-up slices.

This order gives a deployable private tool quickly while keeping the highest-risk flows, especially login-only collection downloads, behind a proven job and file-management base.
