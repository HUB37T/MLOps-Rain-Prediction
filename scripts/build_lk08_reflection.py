"""Render the short reflection; requires reportlab and pypdfium2 for preview."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


repo = Path(__file__).resolve().parents[1]
output = repo / "output/pdf"
output.mkdir(parents=True, exist_ok=True)
pdf = output / "LK08-Refleksi-Code-as-a-Trigger.pdf"
styles = getSampleStyleSheet()
body = ParagraphStyle("BodyCustom", parent=styles["BodyText"], fontSize=11,
                      leading=17, spaceAfter=12, alignment=TA_JUSTIFY)
title = ParagraphStyle("TitleCustom", parent=styles["Title"], fontSize=20,
                       leading=25, textColor=colors.HexColor("#18384a"), spaceAfter=18)
story = [Paragraph("LK-08 | MLOps Rain Prediction", styles["Normal"]), Spacer(1, 12),
         Paragraph("Code as a Trigger", title),
         Paragraph("Refleksi otomatisasi pengujian, pelatihan dan validasi model", styles["Heading2"]),
         Spacer(1, 8)]
text = (repo / "docs/lk08-refleksi.md").read_text(encoding="utf-8")
for paragraph in text.split("\n\n")[1:]:
    story.append(Paragraph(" ".join(paragraph.splitlines()), body))


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#cbd5df"))
    canvas.line(2*cm, 1.6*cm, 19*cm, 1.6*cm)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(2*cm, 1.1*cm, "Rain Prediction | Refleksi LK-08")
    canvas.drawRightString(19*cm, 1.1*cm, str(doc.page))
    canvas.restoreState()


SimpleDocTemplate(str(pdf), pagesize=(21*cm, 29.7*cm), rightMargin=2*cm,
                  leftMargin=2*cm, topMargin=1.8*cm, bottomMargin=2*cm).build(
                      story, onFirstPage=footer, onLaterPages=footer)
import pypdfium2 as pdfium
with pdfium.PdfDocument(str(pdf)) as document:
    for number, page in enumerate(document):
        page.render(scale=1.3).to_pil().save(output / f"lk08-preview-{number+1}.png")
    print(f"PDF created: {pdf}; pages={len(document)}")
