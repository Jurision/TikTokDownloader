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


class PrivatePanelExecutor:
    def __init__(self, volume_root: Path):
        self.volume_root = Path(volume_root)

    async def execute(self, job: JobRecord) -> JobExecutionResult:
        if job.kind == JobKind.DOUYIN_SINGLE:
            return await self.download_douyin_single(job)
        raise NotImplementedError(f"Unsupported job kind: {job.kind.value}")

    async def download_douyin_single(self, job: JobRecord) -> JobExecutionResult:
        from src.application import TikTokDownloader
        from src.application.main_terminal import TikTok

        job_output = self.volume_root / "private_panel" / "jobs" / job.id / "files"
        job_output.mkdir(parents=True, exist_ok=True)
        async with TikTokDownloader() as downloader:
            downloader.config["Record"] = 0
            downloader.check_config()
            await downloader.check_settings(False)
            downloader.parameter.root = job_output
            downloader.parameter.folder_name = "Download"
            downloader.parameter.download = True
            terminal = TikTok(downloader.parameter, downloader.database)
            root, params, logger = terminal.record.run(terminal.parameter)
            async with logger(root, console=terminal.console, **params) as record:
                ids = await terminal.links.run(job.input_text)
                if not any(ids):
                    raise ValueError("No Douyin work ID found in submitted text")
                await terminal._handle_detail(ids, False, record)
            _ensure_downloaded_files(job_output)

        return JobExecutionResult(
            output_dir=f"private_panel/jobs/{job.id}/files",
            log_tail=f"Downloaded {len(ids)} Douyin work item(s)",
        )
