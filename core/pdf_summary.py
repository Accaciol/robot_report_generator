"""Resumo estático de uma execução e sua apresentação em PDF."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from models import ReportData, Status, SuiteResult


def build_summary(data: ReportData) -> dict:
    """Congela apenas os dados necessários ao PDF, sem evidências nem logs."""
    suites = []
    failures = []

    def collect(suite: SuiteResult, parents: tuple[str, ...] = ()) -> None:
        label = " / ".join((*parents, suite.name))
        if suite.tests:
            suites.append({
                "name": label,
                "total": len(suite.tests),
                "passed": sum(test.status == Status.PASS for test in suite.tests),
                "failed": sum(test.status == Status.FAIL for test in suite.tests),
                "skipped": sum(test.status == Status.SKIP for test in suite.tests),
            })
            failures.extend({"suite": label, "test": test.name} for test in suite.tests
                            if test.status == Status.FAIL)
        for child in suite.suites:
            collect(child, (*parents, suite.name))

    for suite in data.suites:
        collect(suite)
    return {
        "title": data.title,
        "generated_at": data.generated_at,
        "version": data.version,
        "stats": {"total": data.stats.total, "passed": data.stats.passed,
                  "failed": data.stats.failed, "skipped": data.stats.skipped,
                  "pass_rate": data.stats.pass_rate, "elapsed_s": data.stats.elapsed_s},
        "suites": suites,
        "failures": failures,
    }


def render_pdf(summary: dict, output_path: Path) -> Path:
    """Gera um resumo visual paginado e só promove o arquivo completo."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import CondPageBreak, Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    import reportlab

    ink = colors.HexColor("#18352F")
    muted = colors.HexColor("#60736B")
    green = colors.HexColor("#16805F")
    green_soft = colors.HexColor("#EAF6F0")
    red = colors.HexColor("#CC483E")
    red_soft = colors.HexColor("#FFF1EF")
    amber = colors.HexColor("#D49A2C")
    line = colors.HexColor("#DDE8E1")
    pale = colors.HexColor("#F6F9F7")
    white = colors.white
    page_width, _ = A4
    content_width = page_width - 92

    fonts = Path(reportlab.__file__).parent / "fonts"
    if "SummaryVera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("SummaryVera", str(fonts / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("SummaryVeraBold", str(fonts / "VeraBd.ttf")))
    pdfmetrics.registerFontFamily("SummaryVera", normal="SummaryVera", bold="SummaryVeraBold")

    class DistributionBar(Flowable):
        def __init__(self, stats, width, height=10):
            super().__init__()
            self.stats = stats
            self.width = width
            self.height = height

        def draw(self):
            total = max(float(self.stats.get("total", 0)), 1)
            self.canv.setFillColor(line)
            self.canv.roundRect(0, 0, self.width, self.height, self.height / 2, fill=1, stroke=0)
            position = 0
            for key, color in (("passed", green), ("failed", red), ("skipped", amber)):
                segment = self.width * max(float(self.stats.get(key, 0)), 0) / total
                if segment:
                    self.canv.setFillColor(color)
                    self.canv.rect(position, 0, min(segment, self.width - position), self.height,
                                   fill=1, stroke=0)
                    position += segment

    class LegendItem(Flowable):
        def __init__(self, label, value, color):
            super().__init__()
            self.label = label
            self.value = value
            self.color = color
            self.width = content_width / 3
            self.height = 14

        def draw(self):
            self.canv.setFillColor(self.color)
            self.canv.circle(4, 7, 3.5, fill=1, stroke=0)
            self.canv.setFont("SummaryVera", 8)
            self.canv.setFillColor(ink)
            self.canv.drawString(13, 4, f"{self.label}  {self.value}")

    output_path = Path(output_path)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("PdfBody", parent=styles["BodyText"], fontName="SummaryVera",
                          fontSize=8.5, leading=13, textColor=ink, splitLongWords=True)
    small = ParagraphStyle("PdfSmall", parent=body, fontSize=7.5, leading=11)
    quiet = ParagraphStyle("PdfQuiet", parent=small, textColor=muted)
    eyebrow = ParagraphStyle("PdfEyebrow", parent=small, fontName="SummaryVeraBold",
                             textColor=colors.HexColor("#A9E0C2"), spaceAfter=8)
    hero_title = ParagraphStyle("PdfHeroTitle", parent=body, fontName="SummaryVeraBold",
                                fontSize=17, leading=22, textColor=white, spaceAfter=10)
    hero_meta = ParagraphStyle("PdfHeroMeta", parent=small, textColor=colors.HexColor("#D8EDE3"))
    heading = ParagraphStyle("PdfHeading", parent=body, fontName="SummaryVeraBold", fontSize=12,
                             leading=17, spaceBefore=20, spaceAfter=9)
    card_label = ParagraphStyle("PdfCardLabel", parent=small, textColor=muted, spaceAfter=7)
    card_value = ParagraphStyle("PdfCardValue", parent=body, fontName="SummaryVeraBold",
                                fontSize=18, leading=21)
    table_head = ParagraphStyle("PdfTableHead", parent=small, fontName="SummaryVeraBold",
                                textColor=muted)
    failure_title = ParagraphStyle("PdfFailureTitle", parent=body, fontName="SummaryVeraBold",
                                   fontSize=8.5, leading=13, spaceAfter=4)

    title = escape(str(summary["title"]))
    date = escape(str(summary["generated_at"]))
    version = escape(str(summary["version"]))
    stats = summary["stats"]
    status_label = "COM FALHAS" if stats["failed"] else "SEM FALHAS"
    status_color = "#FFD4CE" if stats["failed"] else "#BDF0CE"
    hero = Table([[[
        Paragraph("ROBOT REPORTS  /  RESUMO DE EXECUÇÃO", eyebrow),
        Paragraph(title, hero_title),
        Paragraph("<font color='" + status_color + "'><b>" + status_label + "</b></font>"
                  " &nbsp;&nbsp; | &nbsp;&nbsp; " + date + " &nbsp;&nbsp; | &nbsp;&nbsp; " + version,
                  hero_meta),
    ]]], colWidths=[content_width], hAlign="LEFT")
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ink),
        ("LEFTPADDING", (0, 0), (-1, -1), 19), ("RIGHTPADDING", (0, 0), (-1, -1), 19),
        ("TOPPADDING", (0, 0), (-1, -1), 18), ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
    ]))
    story = [hero, Paragraph("Visão executiva", heading)]

    def metric_card(label, value, tint, value_color=ink):
        value_style = ParagraphStyle("Value" + label, parent=card_value, textColor=value_color)
        card = Table([[Paragraph(label, card_label)], [Paragraph(escape(str(value)), value_style)]],
                     colWidths=[(content_width - 18) / 3 - 20])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), tint),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 11),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 11),
        ]))
        return card

    card_specs = [
        ("CENÁRIOS", stats["total"], pale, ink),
        ("PASSOU", stats["passed"], green_soft, green),
        ("FALHOU", stats["failed"], red_soft, red),
        ("IGNORADO", stats["skipped"], colors.HexColor("#FFF8E9"), amber),
        ("SUCESSO", f'{float(stats["pass_rate"]):.1f}%', pale, ink),
        ("DURAÇÃO", f'{float(stats["elapsed_s"]):.1f}s', pale, ink),
    ]
    card_width = (content_width - 18) / 3
    grid = Table([
        [metric_card(*card_specs[0]), "", metric_card(*card_specs[1]), "", metric_card(*card_specs[2])],
        ["", "", "", "", ""],
        [metric_card(*card_specs[3]), "", metric_card(*card_specs[4]), "", metric_card(*card_specs[5])],
    ], colWidths=[card_width, 9, card_width, 9, card_width], rowHeights=[None, 9, None],
       hAlign="LEFT")
    grid.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.extend([grid, Spacer(1, 16), Paragraph("Distribuição dos resultados", small),
                  Spacer(1, 6), DistributionBar(stats, content_width, 12), Spacer(1, 7)])
    legend = Table([[
        LegendItem("Passou", stats["passed"], green),
        LegendItem("Falhou", stats["failed"], red),
        LegendItem("Ignorado", stats["skipped"], amber),
    ]], colWidths=[content_width / 3] * 3, hAlign="LEFT")
    legend.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(legend)

    story.extend([CondPageBreak(105), Paragraph("Resumo por suíte", heading)])
    if summary["suites"]:
        rows = [[Paragraph(text, table_head) for text in ("SUÍTE", "DISTRIBUIÇÃO", "TOTAL", "PASS", "FAIL")]]
        for suite in summary["suites"]:
            rows.append([
                Paragraph(escape(str(suite["name"])), small),
                DistributionBar(suite, 86, 7),
                Paragraph(str(suite["total"]), small),
                Paragraph(str(suite["passed"]), small),
                Paragraph(str(suite["failed"]), small),
            ])
        table = Table(rows, colWidths=[255, 105, 48, 48, 47], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), green_soft),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, pale]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, line),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("Nenhuma suíte com testes nesta execução.", quiet))

    story.extend([CondPageBreak(105), Paragraph("Testes com falha", heading)])
    if summary["failures"]:
        for failure in summary["failures"]:
            failure_card = Table([[[
                Paragraph(escape(str(failure["test"])), failure_title),
                Paragraph(escape(str(failure["suite"])), quiet),
            ]]], colWidths=[content_width], hAlign="LEFT")
            failure_card.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), red_soft),
                ("LINEBEFORE", (0, 0), (0, -1), 3, red),
                ("LEFTPADDING", (0, 0), (-1, -1), 13),
                ("RIGHTPADDING", (0, 0), (-1, -1), 13),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]))
            story.append(KeepTogether([
                failure_card, Spacer(1, 7),
            ]))
    else:
        no_failures = Table([[Paragraph("Nenhum teste com falha nesta execução.", body)]],
                            colWidths=[content_width], hAlign="LEFT")
        no_failures.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), green_soft),
            ("LINEBEFORE", (0, 0), (0, -1), 3, green),
            ("LEFTPADDING", (0, 0), (-1, -1), 13),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(no_failures)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(doc.leftMargin, 42, A4[0] - doc.rightMargin, 42)
        canvas.setFont("SummaryVera", 8)
        canvas.setFillColor(muted)
        canvas.drawString(doc.leftMargin, 27, "ROBOT REPORTS  /  RESUMO DE EXECUÇÃO")
        canvas.drawRightString(A4[0] - doc.rightMargin, 27, f"Página {doc.page}")
        canvas.restoreState()

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_path.parent, prefix=f".{output_path.stem}.",
                                         suffix=".pdf", delete=False) as stream:
            temporary = Path(stream.name)
        document = SimpleDocTemplate(str(temporary), pagesize=A4, leftMargin=46, rightMargin=46,
                                     topMargin=42, bottomMargin=57, title=str(summary["title"]))
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        os.replace(temporary, output_path)
        return output_path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
