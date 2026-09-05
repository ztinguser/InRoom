import base64
import json
import wave
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from websockets.sync.client import connect

from backend.config import Settings
from backend.tts_terms import TTS_REPLACEMENTS


def prepare_speech_text(text: str) -> str:
    for original, spoken in TTS_REPLACEMENTS.items():
        text = text.replace(original, spoken)
    return text


def main() -> None:
    settings = Settings()
    api_key = settings.dashscope_api_key.get_secret_value()
    if not api_key or not settings.qwen_tts_voice:
        raise RuntimeError("请配置 DASHSCOPE_API_KEY 和 QWEN_TTS_VOICE")

    url = (
        "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        f"?model={settings.qwen_tts_model}"
    )
    started = perf_counter()
    deadline = started + 60
    first_audio = None
    audio = bytearray()
    usages = []

    with connect(
        url,
        additional_headers={"Authorization": f"Bearer {api_key}"},
        open_timeout=10,
        close_timeout=5,
    ) as ws:

        def send(event_type: str, **fields) -> None:
            ws.send(
                json.dumps(
                    {
                        "event_id": uuid4().hex,
                        "type": event_type,
                        **fields,
                    }
                )
            )

        # 我们发出
        send(
            "session.update",
            session={
                "voice": settings.qwen_tts_voice,
                "mode": "server_commit",
                "language_type": "Auto",
                "response_format": "pcm",
                "sample_rate": 24000,
            },
        )

        while True:
            remaining = deadline - perf_counter()
            if remaining <= 0:
                raise TimeoutError("TTS 探针超过 60 秒")

            event = json.loads(ws.recv(timeout=remaining))
            event_type = event["type"]

            # 服务端返回
            if event_type == "session.updated":
                # 我们发出，提交待朗读文本
                question = "你项目用了FastAPI、Redis和PostgreSQL数据库，对吗？"
                send(
                    "input_text_buffer.append",
                    text=prepare_speech_text(question),
                )
                # 我们发出，告诉服务端后面没有更多文本
                send("session.finish")

            # 服务端返回一段音频
            elif event_type == "response.audio.delta":
                chunk = base64.b64decode(event["delta"])
                if chunk and first_audio is None:
                    first_audio = perf_counter() - started
                audio.extend(chunk)

            # 服务端返回，一次合成响应结束，携带状态和用量
            elif event_type == "response.done":
                result = event["response"]
                if result["status"] != "completed":
                    raise RuntimeError(f"TTS 响应失败：{result['status']}")
                usages.append(result.get("usage"))

            elif event_type == "error":
                raise RuntimeError(f"TTS 服务错误：{event['error']}")

            # 服务端返回，所有响应生成完毕
            elif event_type == "session.finished":
                break

    if not audio or not usages:
        raise RuntimeError("会话结束，但没有收到音频或完成响应")

    path = Path("probe-output/tts-05.wav")
    path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(audio)

    print(f"model={settings.qwen_tts_model}")
    print(f"voice={settings.qwen_tts_voice}")
    print("region=cn-beijing")
    print("format=PCM signed 16-bit little-endian, mono, 24000Hz")
    print(f"first_audio_seconds={first_audio}")
    print(f"elapsed={perf_counter() - started:.2f}s")
    print(f"audio_seconds={len(audio) / (24000 * 2):.2f}")
    print(f"usage={usages}")
    print(f"audio={path.resolve()}")


if __name__ == "__main__":
    main()
