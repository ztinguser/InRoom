import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.parsing import process as parser_process
from backend.parsing.pdf import extract_pdf
from backend.parsing.schemas import PdfParseError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def children(monkeypatch):
    original = subprocess.Popen
    started = []

    def track(args, **kwargs):
        child = original(args, **kwargs)
        started.append((child, kwargs["stdout"]))
        return child

    monkeypatch.setattr(parser_process.subprocess, "Popen", track)
    try:
        yield started
    finally:
        # 测试失败也只回收本测试启动的进程。
        for child, _ in started:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


@pytest.fixture
def stalled_parser(children, monkeypatch, tmp_path):
    tracked = parser_process.subprocess.Popen
    ready = tmp_path / "parser-ready"
    script = (
        "import runpy, sys, time\n"
        "from pathlib import Path\n"
        "import backend.parsing.pdf as pdf\n"
        "def stall(path):\n"
        "    Path(sys.argv[2]).write_text('ready')\n"
        "    time.sleep(60)\n"
        "pdf.extract_pdf = stall\n"
        "runpy.run_module('backend.parsing.child', run_name='__main__')\n"
    )

    def start(args, **kwargs):
        return tracked([args[0], "-c", script, args[-1], str(ready)], **kwargs)

    monkeypatch.setattr(parser_process.subprocess, "Popen", start)
    return ready


@pytest.mark.asyncio
async def test_real_child_returns_same_result_with_unicode_path(children, tmp_path):
    path = tmp_path / "中文 简历.pdf"
    shutil.copyfile(FIXTURES / "text.pdf", path)

    result = await parser_process.extract_pdf_process(path)

    assert result == extract_pdf(path)
    assert len(children) == 1
    child, output = children[0]
    assert child.returncode == 0
    assert output.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "code"),
    [("encrypted", "PDF_ENCRYPTED"), ("broken", "PDF_INVALID")],
)
async def test_known_errors_cross_process_boundary(children, name, code):
    with pytest.raises(PdfParseError) as error:
        await parser_process.extract_pdf_process(FIXTURES / f"{name}.pdf")

    assert error.value.code == code
    child, output = children[0]
    assert child.returncode == 0  # 子进程通过 JSON 返回业务错误。
    assert output.closed


@pytest.mark.asyncio
async def test_unexpected_failure_is_process_error(children, tmp_path):
    with pytest.raises(PdfParseError) as error:
        await parser_process.extract_pdf_process(tmp_path / "missing.pdf")

    assert error.value.code == "PDF_PROCESS_FAILED"
    child, output = children[0]
    assert child.returncode != 0
    assert output.closed


@pytest.mark.asyncio
async def test_timeout_kills_running_parser(children, stalled_parser, tmp_path):
    with pytest.raises(PdfParseError) as error:
        await parser_process.extract_pdf_process(tmp_path / "unused.pdf", 5)

    assert error.value.code == "PDF_TIMEOUT"
    assert stalled_parser.exists(), "子进程应已进入解析函数，而非仅在启动阶段超时"
    child, output = children[0]
    assert child.poll() is not None
    assert child.returncode != 0
    assert output.closed


@pytest.mark.asyncio
async def test_cancellation_stops_parser_and_keeps_loop_responsive(
    children, stalled_parser, tmp_path
):
    task = asyncio.create_task(
        parser_process.extract_pdf_process(tmp_path / "unused.pdf")
    )
    try:
        async with asyncio.timeout(10):
            while not stalled_parser.exists():
                await asyncio.sleep(0.05)

        # 解析卡住期间，其他协程仍能调度。
        for _ in range(3):
            await asyncio.sleep(0.05)
            assert not task.done()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        child, output = children[0]
        assert child.poll() is not None
        assert child.returncode != 0
        assert output.closed
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
