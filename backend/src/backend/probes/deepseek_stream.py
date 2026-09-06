import argparse
import json
from time import perf_counter

import httpx

from backend.core.config import Settings


def main(cancel: bool = False) -> None:
    settings = Settings()
    api_key = settings.deepseek_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("请在 .env 中配置 DEEPSEEK_API_KEY")

    started = perf_counter()
    first_text = None
    cancel_started = None
    finish_reason = None
    usage = None
    model = None
    chunks = 0
    done = False

    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        with client.stream(
            "POST",
            settings.deepseek_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.deepseek_model,
                "thinking": {"type": "disabled"},
                "stream": True,
                "stream_options": {"include_usage": True},
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "请用约 400 字解释 Python 的事件循环、"
                            "协程与 await 的关系，并给出一个简单示例。"
                        ),
                    }
                ],
            },
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue

                payload = line.removeprefix("data:").strip()
                if payload == "[DONE]":
                    done = True
                    break

                data = json.loads(payload)
                model = data.get("model") or model
                if data.get("usage") is not None:
                    usage = data["usage"]

                choices = data.get("choices", [])
                if not choices:
                    continue

                choice = choices[0]
                finish_reason = choice.get("finish_reason") or finish_reason
                text = choice.get("delta", {}).get("content") or ""
                if not text:
                    continue

                if first_text is None:
                    first_text = perf_counter() - started

                chunks += 1
                print(text, end="", flush=True)

                if cancel and chunks >= 10 and finish_reason is None:
                    cancel_started = perf_counter()
                    break

    closed = perf_counter()
    print()
    print(f"model={model}")
    print(f"first_text_seconds={first_text}")
    print(f"elapsed={closed - started:.2f}s")
    print(f"content_chunks={chunks}")
    print(f"finish_reason={finish_reason}, done={done}")
    print(f"usage={usage}")

    if cancel_started is not None:
        print(f"status=cancelled, close_seconds={closed - cancel_started:.4f}")
    elif not done or finish_reason != "stop":
        raise RuntimeError("流式响应没有正常结束")
    else:
        print("status=completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cancel", action="store_true")
    args = parser.parse_args()
    main(cancel=args.cancel)
