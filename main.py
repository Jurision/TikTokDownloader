import os
from asyncio import CancelledError
from asyncio import run as run_async

from src.private_panel.app import create_panel_app
from uvicorn import Config, Server


PANEL_MODE_VALUES = {"1", "true", "yes"}


def should_run_panel_mode() -> bool:
    return os.environ.get("DOUK_PANEL_MODE", "").lower() in PANEL_MODE_VALUES


def panel_host() -> str:
    return os.environ.get("DOUK_PANEL_HOST", "127.0.0.1")


def panel_port() -> int:
    return int(os.environ.get("DOUK_PANEL_PORT", "5555"))


def run_panel() -> None:
    app = create_panel_app(os.environ.get("DOUK_PANEL_VOLUME", "Volume"))
    Server(Config(app=app, host=panel_host(), port=panel_port(), log_level="info")).run()


async def run_cli() -> None:
    from src.application import TikTokDownloader

    async with TikTokDownloader() as downloader:
        try:
            await downloader.run()
        except (
                KeyboardInterrupt,
                CancelledError,
        ):
            return


def main() -> None:
    if should_run_panel_mode():
        run_panel()
        return

    run_async(run_cli())


if __name__ == "__main__":
    main()
