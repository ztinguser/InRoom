from pathlib import Path

import pytest

from backend.parsing.pdf import extract_pdf
from backend.parsing.schemas import PdfParseError

FIXTURES = Path(__file__).parent / "fixtures"


def test_text_keeps_pages_coordinates_and_stable_ids():
    result = extract_pdf(FIXTURES / "text.pdf")
    assert result.page_count == 2
    assert result.review_pages == []
    first = "".join(block.text for block in result.blocks if block.page == 1)
    second = " ".join(block.text for block in result.blocks if block.page == 2)
    assert "合成简历：后端开发" in first
    assert "Python" in first and "PostgreSQL" in first
    assert second == "Project: InRoom"
    assert len({block.block_id for block in result.blocks}) == len(result.blocks)
    for block in result.blocks:
        left, top, right, bottom = block.bbox
        assert 0 <= left < right <= 600
        assert 0 <= top < bottom <= 800
    assert result == extract_pdf(FIXTURES / "text.pdf")


def test_columns_keep_separate_positions():
    result = extract_pdf(FIXTURES / "columns.pdf")
    blocks = {block.text: block for block in result.blocks}
    assert set(blocks) == {"LEFT_ALPHA", "LEFT_BETA", "RIGHT_ALPHA", "RIGHT_BETA"}
    assert blocks["LEFT_ALPHA"].bbox[0] == pytest.approx(60)
    assert blocks["RIGHT_ALPHA"].bbox[0] == pytest.approx(330)
    assert blocks["LEFT_ALPHA"].bbox[1] < blocks["LEFT_BETA"].bbox[1]


@pytest.mark.parametrize("name", ["scan", "blank"])
def test_pages_without_text_need_review(name):
    result = extract_pdf(FIXTURES / f"{name}.pdf")
    assert result.page_count == 1
    assert result.blocks == []
    assert result.review_pages == [1]


def test_mixed_page_keeps_text_but_still_needs_review():
    result = extract_pdf(FIXTURES / "mixed.pdf")
    assert " ".join(block.text for block in result.blocks) == "Readable header"
    assert result.review_pages == [1]


def test_exact_page_limit_is_allowed():
    result = extract_pdf(FIXTURES / "limit.pdf")
    assert result.page_count == 20
    assert result.review_pages == list(range(1, 21))


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("too_many", "PDF_TOO_MANY_PAGES"),
        ("encrypted", "PDF_ENCRYPTED"),
        ("owner_encrypted", "PDF_ENCRYPTED"),
        ("empty", "PDF_INVALID"),
        ("broken", "PDF_INVALID"),
    ],
)
def test_invalid_documents_have_explicit_error_codes(name, code):
    with pytest.raises(PdfParseError) as error:
        extract_pdf(FIXTURES / f"{name}.pdf")
    assert error.value.code == code


def test_missing_file_is_not_reported_as_invalid_pdf(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_pdf(tmp_path / "missing.pdf")
