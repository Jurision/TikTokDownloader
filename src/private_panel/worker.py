import asyncio

from .executor import PrivatePanelExecutor
from .jobs import JobStore


def _summarize_exception(exc: Exception, limit: int = 4000) -> str:
    summary = f"{type(exc).__name__}: {exc}".replace("\r", " ").replace("\n", " ")
    if len(summary) <= limit:
        return summary
    if limit <= 0:
        return ""
    ellipsis = "..."
    if limit <= len(ellipsis):
        return ellipsis[:limit]
    return f"{summary[: limit - len(ellipsis)]}{ellipsis}"


async def run_one_job(store: JobStore, executor: PrivatePanelExecutor) -> bool:
    job = store.claim_next_queued()
    if job is None:
        return False
    try:
        result = await executor.execute(job)
    except Exception as exc:
        summary = _summarize_exception(exc)
        store.mark_failed(job.id, summary, log_tail=summary)
        return True
    store.mark_succeeded(job.id, result.output_dir, log_tail=result.log_tail)
    return True


async def worker_loop(
    store: JobStore,
    executor: PrivatePanelExecutor,
    poll_seconds: float = 2.0,
) -> None:
    while True:
        try:
            processed = await run_one_job(store, executor)
        except Exception:
            await asyncio.sleep(poll_seconds)
            continue
        if not processed:
            await asyncio.sleep(poll_seconds)
