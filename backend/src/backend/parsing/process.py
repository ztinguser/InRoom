import asyncio
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryFile

from backend.parsing.schemas import PdfParseError, PdfText


async def extract_pdf_process(
    path: Path,
    timeout_seconds: float = 30,
) -> PdfText:
    with TemporaryFile() as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "backend.parsing.child",
                str(path.resolve()),
            ],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.DEVNULL,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            ),
        )

        try:
            try:
                async with asyncio.timeout(timeout_seconds):
                    while process.poll() is None:
                        await asyncio.sleep(0.1)
            except TimeoutError as exc:
                raise PdfParseError("PDF_TIMEOUT", "PDF 解析超时") from exc

            if process.returncode != 0:
                raise PdfParseError("PDF_PROCESS_FAILED", "PDF 解析进程异常退出")

            output.seek(0)
            data = json.load(output)
            if "error" in data:
                error = data["error"]
                raise PdfParseError(error["code"], error["message"])

            return PdfText.model_validate(data["result"])
        finally:
            if process.poll() is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await asyncio.to_thread(process.wait)
