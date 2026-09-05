import logging


def setup_logging(level: str) -> None:
    """
    提取共用的日志初始化
    :param level:
    :return:
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
