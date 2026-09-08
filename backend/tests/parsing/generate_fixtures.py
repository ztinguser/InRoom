"""仅用于重新生成合成夹具，需要 reportlab、pypdf 和 Pillow。"""

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).parent / "fixtures"
ROOT.mkdir(exist_ok=True)
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

canvas = Canvas(str(ROOT / "text.pdf"), pagesize=(600, 800), invariant=1)
canvas.setFont("STSong-Light", 16)
canvas.drawString(60, 720, "合成简历：后端开发")
canvas.setFont("Helvetica", 12)
canvas.drawString(60, 680, "Python PostgreSQL")
canvas.showPage()
canvas.setFont("Helvetica", 12)
canvas.drawString(60, 720, "Project: InRoom")
canvas.save()

canvas = Canvas(str(ROOT / "columns.pdf"), pagesize=(600, 800), invariant=1)
canvas.drawString(60, 720, "LEFT_ALPHA")
canvas.drawString(330, 720, "RIGHT_ALPHA")
canvas.drawString(60, 680, "LEFT_BETA")
canvas.drawString(330, 680, "RIGHT_BETA")
canvas.save()

scan = Image.new("RGB", (800, 400), "white")
ImageDraw.Draw(scan).text(
    (40, 60), "Synthetic scanned resume", fill="black", font_size=32
)
image_bytes = BytesIO()
scan.save(image_bytes, format="PNG")
for name in ["scan", "mixed"]:
    canvas = Canvas(str(ROOT / f"{name}.pdf"), pagesize=(600, 800), invariant=1)
    canvas.drawImage(ImageReader(image_bytes), 60, 400, width=480, height=240)
    if name == "mixed":
        canvas.drawString(60, 720, "Readable header")
    canvas.save()

for name, count in [("blank", 1), ("limit", 20), ("too_many", 21), ("empty", 0)]:
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=600, height=800)
    writer.write(ROOT / f"{name}.pdf")

for name, password in [("encrypted", "test-password"), ("owner_encrypted", "")]:
    writer = PdfWriter(clone_from=ROOT / "text.pdf")
    writer.encrypt(user_password=password, owner_password="test-owner-password")
    writer.write(ROOT / f"{name}.pdf")

(ROOT / "broken.pdf").write_bytes(b"%PDF-1.7\nnot a PDF object tree\n")
