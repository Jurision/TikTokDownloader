import asyncio
import html
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .auth import require_panel_user
from .executor import PrivatePanelExecutor
from .files import list_files, resolve_job_file
from .jobs import JobStore
from .models import JobCreate, JobKind, JobRecord, PanelUser
from .worker import worker_loop


INTERRUPTED_JOB_ERROR = "Worker restarted before completion"
MAX_HEALTHY_WORKER_ERRORS = 0
SUPPORTED_JOB_OPTIONS = (
    (JobKind.DOUYIN_SINGLE, "Douyin single work link"),
    (JobKind.DOUYIN_ACCOUNT_POSTS, "Douyin account posts"),
    (JobKind.DOUYIN_ACCOUNT_LIKED, "Douyin account liked works"),
    (JobKind.DOUYIN_FAVORITES, "My Douyin favorites"),
    (JobKind.DOUYIN_MIX, "Douyin mix or collection link"),
)
SUPPORTED_JOB_KINDS = {kind for kind, _label in SUPPORTED_JOB_OPTIONS}


def _job_store(volume_root: Path) -> JobStore:
    return JobStore(Path(volume_root) / "private_panel" / "jobs.db")


def _panel_html(user: PanelUser, jobs: list[JobRecord]) -> str:
    rows = "\n".join(
        f"<tr><td>{html.escape(job.id)}</td><td>{html.escape(job.kind.value)}</td>"
        f"<td>{html.escape(job.status.value)}</td><td>{html.escape(job.log_tail)}</td></tr>"
        for job in jobs
    )
    options = "\n".join(
        f'      <option value="{html.escape(kind.value)}">{html.escape(label)}</option>'
        for kind, label in SUPPORTED_JOB_OPTIONS
    )
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Private Download Panel</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #18201b; }}
    main {{ max-width: 1040px; margin: 0 auto; }}
    textarea, select, button {{ font: inherit; }}
    textarea {{ width: 100%; min-height: 120px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
    th, td {{ border-bottom: 1px solid #d9e2dc; padding: 8px; text-align: left; }}
    button {{ padding: 8px 12px; background: #1d7f5f; color: white; border: 0; border-radius: 6px; }}
  </style>
</head>
<body>
<main>
  <h1>Private Download Panel</h1>
  <p>Signed in as {html.escape(user.name or user.id)}</p>
  <form id="job-form">
    <label for="kind">Source type</label>
    <select id="kind" name="kind">
{options}
    </select>
    <p><label for="input_text">Links or task input</label></p>
    <textarea id="input_text" name="input_text"></textarea>
    <p><button type="submit">Start job</button></p>
  </form>
  <h2>Recent jobs</h2>
  <table>
    <thead><tr><th>ID</th><th>Kind</th><th>Status</th><th>Latest log</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</main>
<script>
document.getElementById("job-form").addEventListener("submit", async (event) => {{
  event.preventDefault();
  const response = await fetch("/downloads/api/jobs", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{
      kind: document.getElementById("kind").value,
      input_text: document.getElementById("input_text").value
    }})
  }});
  if (response.ok) {{
    window.location.reload();
  }} else {{
    alert("Job submission failed");
  }}
}});
</script>
</body>
</html>
"""


def _validated_output_dir(job: JobRecord) -> str:
    if not job.output_dir:
        return ""
    expected = f"private_panel/jobs/{job.id}/files"
    if job.output_dir != expected:
        raise ValueError("Invalid job output directory")
    return job.output_dir


def _auth_health() -> dict[str, bool]:
    import os

    return {
        "trusted_proxy": bool(os.environ.get("DOUK_TRUSTED_PROXY_SECRET")),
        "token": bool(os.environ.get("DOUK_PRIVATE_TOKEN")),
    }


def _summarize_worker_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".replace("\r", " ").replace("\n", " ")[:500]


def _worker_state(app: FastAPI, start_worker: bool) -> str:
    if getattr(app.state, "worker_error_count", 0) > MAX_HEALTHY_WORKER_ERRORS:
        return "degraded"
    if not start_worker:
        return "disabled"
    task = getattr(app.state, "worker_task", None)
    if task is None:
        return "missing"
    if task.cancelled():
        return "cancelled"
    if task.done():
        if task.exception():
            return "failed"
        return "stopped"
    return "running"


def create_panel_app(volume_root: Path | str = "Volume", start_worker: bool = True) -> FastAPI:
    root = Path(volume_root)
    root.mkdir(parents=True, exist_ok=True)
    store = _job_store(root)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not start_worker:
            yield
            return

        executor = PrivatePanelExecutor(root)
        store.mark_interrupted_running_jobs_failed(INTERRUPTED_JOB_ERROR)
        app.state.worker_error_count = 0
        app.state.worker_last_error = ""

        def record_worker_error(exc: Exception) -> None:
            app.state.worker_error_count += 1
            app.state.worker_last_error = _summarize_worker_error(exc)

        worker_task = asyncio.create_task(worker_loop(store, executor, on_error=record_worker_error))
        app.state.worker_task = worker_task
        try:
            yield
        finally:
            worker_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await worker_task

    app = FastAPI(
        title="Private Download Panel",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.state.job_store = store
    app.state.volume_root = root

    @app.get("/downloads/api/health")
    async def health():
        await asyncio.sleep(0)
        auth = _auth_health()
        worker = _worker_state(app, start_worker)
        ok = auth["trusted_proxy"] and worker not in {
            "missing",
            "cancelled",
            "degraded",
            "failed",
            "stopped",
        }
        return JSONResponse(
            {
                "ok": ok,
                "service": "private-download-panel",
                "worker": worker,
                "worker_error": getattr(app.state, "worker_last_error", ""),
                "auth": auth,
            },
            status_code=200 if ok else 503,
        )

    @app.get("/downloads/", response_class=HTMLResponse)
    async def index(user: PanelUser = Depends(require_panel_user)):
        return HTMLResponse(_panel_html(user, store.list_jobs()))

    @app.get("/downloads/api/jobs")
    async def list_panel_jobs(user: PanelUser = Depends(require_panel_user)):
        return store.list_jobs()

    @app.post("/downloads/api/jobs")
    async def create_job(
        payload: JobCreate,
        user: PanelUser = Depends(require_panel_user),
    ):
        if payload.kind not in SUPPORTED_JOB_KINDS:
            raise HTTPException(status_code=400, detail="Unsupported job kind")
        return store.create_job(payload.kind, payload.input_text)

    @app.get("/downloads/api/jobs/{job_id}")
    async def get_job(job_id: str, user: PanelUser = Depends(require_panel_user)):
        try:
            return store.get_job(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None

    @app.get("/downloads/api/jobs/{job_id}/files")
    async def get_job_files(job_id: str, user: PanelUser = Depends(require_panel_user)):
        try:
            job = store.get_job(job_id)
            output_dir = _validated_output_dir(job)
            return list_files(root, output_dir) if output_dir else []
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file path") from None

    @app.get("/downloads/api/jobs/{job_id}/files/{file_path:path}")
    async def download_job_file(
        job_id: str,
        file_path: str,
        user: PanelUser = Depends(require_panel_user),
    ):
        try:
            job = store.get_job(job_id)
            output_dir = _validated_output_dir(job)
            if not output_dir:
                raise FileNotFoundError(file_path)
            resolved = resolve_job_file(root, output_dir, file_path)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found") from None
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found") from None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file path") from None
        return FileResponse(resolved)

    return app
