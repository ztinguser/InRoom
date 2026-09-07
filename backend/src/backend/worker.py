import asyncio
import logging
import signal
import sys

from backend.core.config import Settings
from backend.core.log import setup_logging
from backend.jobs.worker import serve as serve_jobs
from backend.outbox.worker import serve as serve_outbox

logger = logging.getLogger(__name__)


async def start(settings: Settings) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop(signum, frame):
        loop.call_soon_threadsafe(stop.set)

    previous = {
        sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(serve_jobs(settings, stop))
            group.create_task(serve_outbox(settings, stop))
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> None:
    settings = Settings()
    settings.validate_production()
    setup_logging(settings.log_level)

    logger.info("按 Ctrl+C 停止接单，当前任务结束后退出")
    asyncio.run(
        start(settings),
        loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None,
    )


if __name__ == "__main__":
    main()
