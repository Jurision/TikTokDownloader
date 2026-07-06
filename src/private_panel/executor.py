from dataclasses import dataclass
from pathlib import Path

from .models import JobKind, JobRecord


@dataclass(frozen=True)
class JobExecutionResult:
    output_dir: str
    log_tail: str


def _ensure_downloaded_files(job_output: Path) -> None:
    download_dir = job_output / "Download"
    if not download_dir.is_dir():
        raise RuntimeError("Douyin single-link download produced no files")
    if not any(path.is_file() for path in download_dir.rglob("*")):
        raise RuntimeError("Douyin single-link download produced no files")


def _ensure_output_files(job_output: Path, label: str) -> None:
    for path in job_output.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(job_output)
        if relative.parts and relative.parts[0] == "Data":
            continue
        return
    raise RuntimeError(f"{label} produced no files")


class PrivatePanelExecutor:
    def __init__(self, volume_root: Path):
        self.volume_root = Path(volume_root)

    async def execute(self, job: JobRecord) -> JobExecutionResult:
        if job.kind == JobKind.DOUYIN_SINGLE:
            return await self.download_douyin_single(job)
        if job.kind == JobKind.DOUYIN_ACCOUNT_POSTS:
            return await self.download_douyin_account_posts(job)
        if job.kind == JobKind.DOUYIN_ACCOUNT_LIKED:
            return await self.download_douyin_account_liked(job)
        if job.kind == JobKind.DOUYIN_FAVORITES:
            return await self.download_douyin_favorites(job)
        if job.kind == JobKind.DOUYIN_MIX:
            return await self.download_douyin_mix(job)
        raise NotImplementedError(f"Unsupported job kind: {job.kind.value}")

    def _job_output(self, job: JobRecord) -> Path:
        return self.volume_root / "private_panel" / "jobs" / job.id / "files"

    async def _run_with_terminal(self, job: JobRecord, handler) -> Path:
        from src.application import TikTokDownloader
        from src.application.main_terminal import TikTok

        job_output = self._job_output(job)
        job_output.mkdir(parents=True, exist_ok=True)
        async with TikTokDownloader() as downloader:
            downloader.config["Record"] = 0
            downloader.check_config()
            await downloader.check_settings(False)
            downloader.parameter.root = job_output
            downloader.parameter.folder_name = "Download"
            downloader.parameter.download = True
            terminal = TikTok(downloader.parameter, downloader.database)
            await handler(terminal)
        return job_output

    async def download_douyin_single(self, job: JobRecord) -> JobExecutionResult:
        ids_count = 0

        async def handle(terminal) -> None:
            nonlocal ids_count
            root, params, logger = terminal.record.run(terminal.parameter)
            async with logger(root, console=terminal.console, **params) as record:
                ids = await terminal.links.run(job.input_text)
                if not any(ids):
                    raise ValueError("No Douyin work ID found in submitted text")
                ids_count = len(ids)
                await terminal._handle_detail(ids, False, record)

        job_output = await self._run_with_terminal(job, handle)
        _ensure_downloaded_files(job_output)

        return JobExecutionResult(
            output_dir=f"private_panel/jobs/{job.id}/files",
            log_tail=f"Downloaded {ids_count} Douyin work item(s)",
        )

    async def download_douyin_account_posts(self, job: JobRecord) -> JobExecutionResult:
        return await self._download_douyin_account(
            job,
            tab="post",
            label="Douyin account posts",
            log_tail="Downloaded Douyin account posts",
        )

    async def download_douyin_account_liked(self, job: JobRecord) -> JobExecutionResult:
        return await self._download_douyin_account(
            job,
            tab="favorite",
            label="Douyin account liked works",
            log_tail="Downloaded Douyin account liked works",
            allow_owner_url_fallback=True,
        )

    async def _download_douyin_account(
        self,
        job: JobRecord,
        *,
        tab: str,
        label: str,
        log_tail: str,
        allow_owner_url_fallback: bool = False,
    ) -> JobExecutionResult:
        async def handle(terminal) -> None:
            source = job.input_text.strip()
            if not source and allow_owner_url_fallback:
                source = getattr(terminal.owner, "url", "").strip()
            if not source:
                raise ValueError("Douyin account URL is required")
            sec_user_id = await terminal.check_sec_user_id(source)
            if not sec_user_id:
                raise ValueError("No Douyin account sec_user_id found in submitted URL")
            if not await terminal.deal_account_detail(0, sec_user_id=sec_user_id, tab=tab):
                raise RuntimeError(f"{label} download returned no data")

        job_output = await self._run_with_terminal(job, handle)
        _ensure_output_files(job_output, label)
        return JobExecutionResult(
            output_dir=f"private_panel/jobs/{job.id}/files",
            log_tail=log_tail,
        )

    async def download_douyin_favorites(self, job: JobRecord) -> JobExecutionResult:
        async def handle(terminal) -> None:
            owner_url = getattr(terminal.owner, "url", "").strip()
            if not owner_url:
                raise ValueError("Douyin owner_url.url is required for favorites")
            sec_user_id = await terminal.check_sec_user_id(owner_url)
            if not sec_user_id:
                raise ValueError("No Douyin owner sec_user_id found in owner_url.url")
            if not await terminal._deal_collection_data(sec_user_id):
                raise RuntimeError("Logged-in Douyin favorites download returned no data")

        job_output = await self._run_with_terminal(job, handle)
        _ensure_output_files(job_output, "Logged-in Douyin favorites")
        return JobExecutionResult(
            output_dir=f"private_panel/jobs/{job.id}/files",
            log_tail="Downloaded logged-in Douyin favorites",
        )

    async def download_douyin_mix(self, job: JobRecord) -> JobExecutionResult:
        async def handle(terminal) -> None:
            source = job.input_text.strip()
            if not source:
                raise ValueError("Douyin mix or work link is required")
            mix_id, id_, _title = await terminal._check_mix_id(source, False)
            if not id_:
                raise ValueError("No Douyin mix or work ID found in submitted link")
            if not await terminal.deal_mix_detail(mix_id, id_):
                raise RuntimeError("Douyin mix download returned no data")

        job_output = await self._run_with_terminal(job, handle)
        _ensure_output_files(job_output, "Douyin mix")
        return JobExecutionResult(
            output_dir=f"private_panel/jobs/{job.id}/files",
            log_tail="Downloaded Douyin mix works",
        )
