from pydantic import BaseModel


class TextBlock(BaseModel):
    """文字，以及它在第几页、哪个矩形区域"""

    block_id: str
    page: int
    text: str
    bbox: tuple[float, float, float, float]


class PdfText(BaseModel):
    """整个文件的提取结果，以及需要检查的页面"""

    page_count: int
    blocks: list[TextBlock]
    review_pages: list[int]


class PdfParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
