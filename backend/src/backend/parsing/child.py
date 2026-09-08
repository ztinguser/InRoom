import json
import sys
from pathlib import Path

from backend.parsing.pdf import extract_pdf
from backend.parsing.schemas import PdfParseError


def main() -> None:
    try:
        result = extract_pdf(Path(sys.argv[1]))
    except PdfParseError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}))
    else:
        print(json.dumps({"result": result.model_dump()}))


if __name__ == "__main__":
    main()
