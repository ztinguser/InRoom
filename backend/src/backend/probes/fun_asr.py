import argparse
import asyncio
import json
import wave
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from websockets.asyncio.client import connect

from backend.config import Settings


async def main(path: Path) -> None:
    settings = Settings()
    api_key = settings.dashscope_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("请配置 DASHSCOPE_API_KEY")

    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("请使用单声道、16 位 PCM WAV 文件")

        sample_rate = wav.getframerate()
        audio = wav.readframes(wav.getnframes())

    duration = len(audio) / (sample_rate * 2)
    task_id = str(uuid4())
    sentences = []
    finish_sent = None
    started = perf_counter()

    async with asyncio.timeout(duration + 30):
        async with connect(
            "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
            additional_headers={"Authorization": f"Bearer {api_key}"},
            open_timeout=10,
            close_timeout=5,
        ) as ws:

            async def send_command(action: str, payload: dict) -> None:
                await ws.send(
                    json.dumps(
                        {
                            "header": {
                                "action": action,
                                "task_id": task_id,
                                "streaming": "duplex",
                            },
                            "payload": payload,
                        }
                    )
                )

            await send_command(
                "run-task",
                {
                    "task_group": "audio",
                    "task": "asr",
                    "function": "recognition",
                    "model": settings.asr_model,
                    "parameters": {
                        "format": "pcm",
                        "sample_rate": sample_rate,
                    },
                    "input": {},
                },
            )

            event = json.loads(await ws.recv())
            if event["header"]["event"] != "task-started":
                raise RuntimeError(f"ASR 启动失败：{event['header']}")

            async def send_audio() -> None:
                nonlocal finish_sent
                chunk_size = int(sample_rate * 0.1) * 2

                for offset in range(0, len(audio), chunk_size):
                    chunk = audio[offset : offset + chunk_size]
                    await ws.send(chunk)
                    await asyncio.sleep(len(chunk) / (sample_rate * 2))

                finish_sent = perf_counter()
                await send_command("finish-task", {"input": {}})

            async def receive_results() -> None:
                while True:
                    event = json.loads(await ws.recv())
                    event_type = event["header"]["event"]

                    if event_type == "result-generated":
                        sentence = event["payload"]["output"]["sentence"]
                        text = sentence["text"]
                        # 当前句子已转写定稿，可以加入结果
                        if sentence["sentence_end"]:
                            sentences.append(text)
                            print(f"final: {text}")
                        else:
                            print(f"partial: {text}")

                    elif event_type == "task-failed":
                        raise RuntimeError(f"ASR 失败：{event['header']}")

                    # 整个识别任务结束，可以关闭连接
                    elif event_type == "task-finished":
                        if finish_sent is None:
                            raise RuntimeError("音频尚未发完，任务已提前结束")
                        print(f"finish_wait_seconds={perf_counter() - finish_sent:.3f}")
                        return

            async with asyncio.TaskGroup() as tasks:
                # 分块发送 → 等待下一块 → 发送结束指令
                tasks.create_task(send_audio())
                # 持续接收 → 显示临时文字 → 收集最终文字
                tasks.create_task(receive_results())

    print(f"model={settings.asr_model}")
    print(f"task_id={task_id}")
    print("region=cn-beijing")
    print(f"input=PCM16 mono {sample_rate}Hz")
    print(f"audio_seconds={duration:.2f}")
    print(f"elapsed={perf_counter() - started:.2f}s")
    print(f"transcript={''.join(sentences)}")
    print("status=completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.audio))
