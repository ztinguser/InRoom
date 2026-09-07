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
    # HTTP 客户端默认请求日志可能包含 OIDC 回调的 code/state。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
