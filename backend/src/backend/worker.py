import logging

from backend.core.config import Settings
from backend.core.log import setup_logging

logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings()
    settings.validate_production()
    setup_logging(settings.log_level)

    logger.info("Worker initialized, environment=%s", settings.app_env)
    logger.info("No task handlers configured; exiting")


if __name__ == "__main__":
    main()
