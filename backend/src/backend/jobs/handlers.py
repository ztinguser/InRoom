import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

Handler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]


async def demo(payload: dict[str, Any]) -> dict[str, Any]:
    await asyncio.sleep(float(payload.get("seconds", 2)))

    if payload.get("fail"):
        raise RuntimeError("demo task failed")

    return {"message": payload.get("message", "任务完成")}


HANDLERS: dict[str, Handler] = {
    "demo": demo,
}
