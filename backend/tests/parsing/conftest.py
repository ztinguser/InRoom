import asyncio


def pytest_asyncio_loop_factories(config, item):
    # 与 Windows Worker 相同，不依赖 Proactor 的异步子进程支持。
    return {"selector": asyncio.SelectorEventLoop}
