from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from backend.parsing.schemas import PdfParseError, PdfText, TextBlock

MAX_PDF_PAGES = 20


def extract_pdf(path: Path) -> PdfText:
    blocks: list[TextBlock] = []
    review_pages: list[int] = []

    try:
        with pdfplumber.open(path) as pdf:
            if pdf.doc.encryption:
                raise PdfParseError("PDF_ENCRYPTED", "暂不支持加密 PDF")

            page_count = len(pdf.pages)
            if page_count == 0:
                raise PdfParseError("PDF_INVALID", "PDF 没有页面")
            if page_count > MAX_PDF_PAGES:
                raise PdfParseError("PDF_TOO_MANY_PAGES", "PDF 不能超过 20 页")

            for page in pdf.pages:
                words = page.extract_words()
                if not words or page.images:
                    review_pages.append(page.page_number)

                for index, word in enumerate(words, start=1):
                    blocks.append(
                        TextBlock(
                            block_id=f"p{page.page_number}-b{index}",
                            page=page.page_number,
                            text=word["text"],
                            bbox=(
                                word["x0"],
                                word["top"],
                                word["x1"],
                                word["bottom"],
                            ),
                        )
                    )
                page.close()

    except PdfminerException as exc:
        if exc.args and isinstance(exc.args[0], PDFPasswordIncorrect):
            raise PdfParseError("PDF_ENCRYPTED", "暂不支持需要密码的 PDF") from exc
        raise PdfParseError("PDF_INVALID", "PDF 无法解析") from exc

    return PdfText(
        page_count=page_count,
        blocks=blocks,
        review_pages=review_pages,
    )
