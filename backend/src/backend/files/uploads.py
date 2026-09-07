from fastapi import UploadFile

from backend.core.errors import AppError

MAX_PDF_BYTES = 10 * 1024 * 1024


async def read_pdf(upload: UploadFile) -> bytes:
    try:
        content = await upload.read(MAX_PDF_BYTES + 1)
    finally:
        await upload.close()

    if len(content) > MAX_PDF_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", "PDF 不能超过 10 MiB")

    if not content.startswith(b"%PDF-"):
        raise AppError(422, "INVALID_PDF", "文件为空或缺少 PDF 文件头")

    return content
