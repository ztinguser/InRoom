from io import BytesIO

import pytest
from fastapi import UploadFile

from backend.core.errors import AppError
from backend.files.uploads import MAX_PDF_BYTES, read_pdf


@pytest.mark.asyncio
async def test_accepts_exact_size_limit() -> None:
    content = b"%PDF-" + b"x" * (MAX_PDF_BYTES - 5)
    file = BytesIO(content)
    upload = UploadFile(file=file, filename="resume.pdf")

    assert await read_pdf(upload) == content
    assert file.closed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "status", "code"),
    [
        (b"", 422, "INVALID_PDF"),
        (b"not a PDF", 422, "INVALID_PDF"),
        (b"%PDF-" + b"x" * (MAX_PDF_BYTES - 4), 413, "FILE_TOO_LARGE"),
    ],
    ids=["empty", "wrong-header", "too-large"],
)
async def test_rejects_invalid_uploads(content: bytes, status: int, code: str) -> None:
    file = BytesIO(content)
    upload = UploadFile(file=file, filename="resume.pdf")

    with pytest.raises(AppError) as error:
        await read_pdf(upload)

    assert error.value.status == status
    assert error.value.code == code
    assert file.closed


@pytest.mark.asyncio
async def test_read_failure_closes_file() -> None:
    class BrokenFile(BytesIO):
        def read(self, size: int = -1) -> bytes:
            raise OSError("read failed")

    file = BrokenFile()
    upload = UploadFile(file=file)

    with pytest.raises(OSError, match="read failed"):
        await read_pdf(upload)

    assert file.closed
