import base64
import wave
from pathlib import Path

import httpx

from backend.config import Settings


def main() -> None:
    settings = Settings()
    api_key = settings.dashscope_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("请在 .env 中配置 DASHSCOPE_API_KEY")

    with httpx.Client(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        response = client.post(
            "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "qwen-voice-design",
                "input": {
                    "action": "create",
                    "target_model": settings.qwen_tts_model,
                    "preferred_name": "inroom",
                    "voice_prompt": (
                        "成年女性，标准普通话，音色自然清晰，"
                        "语速适中，语气平和专业，适合技术面试交流。"
                    ),
                    "preview_text": (
                        "你好，欢迎参加这次模拟面试。请先介绍一下你最近参与的后端项目。"
                    ),
                },
                "parameters": {
                    "sample_rate": 24000,
                    "response_format": "wav",
                },
            },
        )
        response.raise_for_status()

    data = response.json()
    output = data["output"]
    print(f"voice={output['voice']}")
    print(f"target_model={output['target_model']}")
    print(f"request_id={data.get('request_id')}")

    audio = base64.b64decode(output["preview_audio"]["data"])
    path = Path("probe-output/voice-preview.wav")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)

    with wave.open(str(path), "rb") as wav:
        print(f"sample_rate={wav.getframerate()}")
        print(f"channels={wav.getnchannels()}")
        print(f"sample_width_bytes={wav.getsampwidth()}")
        print(f"duration={wav.getnframes() / wav.getframerate():.2f}s")

    print(f"audio={path.resolve()}")


if __name__ == "__main__":
    main()
