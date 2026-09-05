import json

import httpx
import pytest

from backend.probes import deepseek_stream


def event(text="", finish_reason=None):
    data = {
        "model": "deepseek-v4-flash",
        "choices": [{"delta": {"content": text}, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


class TrackedStream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.consumed = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.consumed += 1
            yield chunk

    def close(self):
        self.closed = True


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    client_class = httpx.Client

    def install(chunks, status_code=200):
        stream = TrackedStream(chunks)
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(
                status_code,
                headers={"Content-Type": "text/event-stream; charset=utf-8"},
                stream=stream,
            )

        def make_client(**kwargs):
            return client_class(
                **kwargs, transport=httpx.MockTransport(handle), trust_env=False
            )

        monkeypatch.setattr(deepseek_stream.httpx, "Client", make_client)
        return stream, requests

    return install


def test_stream_reads_usage_after_text_and_handles_split_utf8(provider, capsys):
    wire = (
        b": heartbeat\n\n"
        + event("协程")
        + event(finish_reason="stop")
        + b'data: {"choices": [], "usage": {"total_tokens": 84}}\n\n'
        + b"data: [DONE]\n\n"
    )
    stream, requests = provider([wire[i : i + 1] for i in range(len(wire))])

    deepseek_stream.main()

    output = capsys.readouterr().out
    assert "协程" in output
    assert "usage={'total_tokens': 84}" in output
    assert "status=completed" in output
    assert "test-only-key" not in output
    assert stream.closed
    assert len(requests) == 1
    assert requests[0].url.path == "/compatible-mode/v1/chat/completions"
    body = json.loads(requests[0].content)
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}


def test_cancel_closes_stream_without_reading_remaining_chunks(provider, capsys):
    chunks = [event("字") for _ in range(10)] + [event("不应读取")]
    stream, _ = provider(chunks)

    deepseek_stream.main(cancel=True)

    output = capsys.readouterr().out
    assert "status=cancelled" in output
    assert "status=completed" not in output
    assert "usage=None" in output
    assert "不应读取" not in output
    assert stream.consumed == 10
    assert stream.closed


@pytest.mark.parametrize(
    "ending",
    [[], [event(finish_reason="length"), b"data: [DONE]\n\n"]],
)
def test_stream_rejects_disconnect_or_truncation(provider, ending, capsys):
    stream, _ = provider([event("部分内容"), *ending])

    with pytest.raises(RuntimeError, match="流式响应没有正常结束"):
        deepseek_stream.main()

    assert stream.closed
    assert "status=completed" not in capsys.readouterr().out


def test_stream_closes_on_http_error(provider):
    stream, _ = provider([], status_code=401)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        deepseek_stream.main()

    assert exc_info.value.response.status_code == 401
    assert stream.closed
