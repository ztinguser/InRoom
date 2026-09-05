import json

import httpx
import pytest
from pydantic import ValidationError

from backend.probes import deepseek


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    requests = []
    result = {
        "model": "deepseek-v4-flash",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {"question": "什么是协程？", "topic": "Python"}
                    )
                },
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 34, "total_tokens": 84},
    }
    response = {"status_code": 200}

    def handle(request):
        requests.append(request)
        return httpx.Response(response["status_code"], json=result)

    client_class = httpx.Client

    def make_client(**kwargs):
        return client_class(
            **kwargs, transport=httpx.MockTransport(handle), trust_env=False
        )

    monkeypatch.setattr(deepseek.httpx, "Client", make_client)
    return response, result, requests


def test_probe_success(provider, capsys: pytest.CaptureFixture[str]) -> None:
    _, _, requests = provider

    deepseek.main()

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/compatible-mode/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-only-key"
    body = json.loads(request.content)
    assert body["model"] == "deepseek-v4-flash"
    assert body["response_format"] == {"type": "json_object"}
    assert body["stream"] is False
    output = capsys.readouterr().out
    assert "什么是协程？" in output
    assert "'total_tokens': 84" in output
    assert "test-only-key" not in output


def test_probe_rejects_http_error(provider) -> None:
    response, _, _ = provider
    response["status_code"] = 401

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        deepseek.main()

    assert exc_info.value.response.status_code == 401


@pytest.mark.parametrize(
    ("finish_reason", "content", "error"),
    [
        ("length", '{"question":', RuntimeError),
        ("stop", '{"question": "什么是协程？"}', ValidationError),
    ],
)
def test_probe_rejects_invalid_output(provider, finish_reason, content, error) -> None:
    _, result, _ = provider
    result["choices"][0] = {
        "finish_reason": finish_reason,
        "message": {"content": content},
    }

    with pytest.raises(error):
        deepseek.main()


def test_probe_requires_key(provider, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, requests = provider
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        deepseek.main()

    assert requests == []
