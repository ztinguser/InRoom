from time import perf_counter

import httpx
from pydantic import BaseModel

from backend.config import Settings


class Question(BaseModel):
    question: str
    topic: str


def main() -> None:
    settings = Settings()
    api_key = settings.deepseek_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("请在 .env 中配置 DEEPSEEK_API_KEY")

    started = perf_counter()

    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        response = client.post(
            settings.deepseek_url + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.deepseek_model,
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": 512,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是 Python 后端面试官。生成一道简短面试题，"
                            "仅输出 JSON，格式示例："
                            '{"question": "什么是生成器？", "topic": "Python"}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": "请围绕 Python 的 async/await 提问。",
                    },
                ],
            },
        )
        response.raise_for_status()

    data = response.json()
    choice = data["choices"][0]
    if choice["finish_reason"] != "stop":
        raise RuntimeError(f"模型未正常完成：{choice['finish_reason']}")

    question = Question.model_validate_json(choice["message"]["content"])

    print(question.model_dump_json(indent=2))
    print(f"model={data.get('model')}")
    print(f"elapsed={perf_counter() - started:.2f}s")
    print(f"usage={data.get('usage')}")


if __name__ == "__main__":
    main()
