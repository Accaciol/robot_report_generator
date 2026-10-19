"""Resumo estático de uma execução e sua apresentação em PDF."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from models import ReportData, Status, SuiteResult

if TYPE_CHECKING:
    from core.sqlite_store import SQLiteStore


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


def _init_fonts() -> None:
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    fonts = Path(reportlab.__file__).parent / "fonts"
    if "SummaryVera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("SummaryVera", str(fonts / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("SummaryVeraBold", str(fonts / "VeraBd.ttf")))
    pdfmetrics.registerFontFamily("SummaryVera", normal="SummaryVera", bold="SummaryVeraBold")


def collect_system_data(store: SQLiteStore, system_id: str) -> dict:
    """Carrega dados detalhados do sistema para inclusão no PDF customizado."""
    metadata, history, directory = store.load(system_id)
    if not history:
        return {
            "id": system_id,
            "name": str(metadata.get("name", system_id)),
            "version": "sem execuções",
            "date": "-",
            "stats": {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "pass_rate": 0.0, "elapsed_s": 0.0},
            "suites": [],
            "failures": [],
            "history": [],
            "slowest": [],
        }

    latest = history[-1]
    suites = []
    failures = []
    slowest = []

    try:
        report_data = store.report_data(metadata, history, directory, "Relatório de Testes")
        summary = build_summary(report_data)
        suites = summary["suites"]
        all_tests = []

        def _gather_tests(suite: SuiteResult, parents: tuple[str, ...] = ()) -> None:
            suite_label = " / ".join((*parents, suite.name))
            for test in suite.tests:
                st_val = test.status.value if hasattr(test.status, "value") else str(test.status)
                all_tests.append({
                    "name": test.name,
                    "suite": suite_label,
                    "status": st_val,
                    "elapsed_s": float(test.elapsed_s or 0.0),
                    "message": getattr(test, "message", "") or "",
                })
            for child in suite.suites:
                _gather_tests(child, (*parents, suite.name))

        for s in report_data.suites:
            _gather_tests(s)

        slowest = sorted(all_tests, key=lambda t: t["elapsed_s"], reverse=True)[:10]
        test_msg_map = {(t["suite"], t["name"]): t.get("message", "") for t in all_tests}
        for fail in summary["failures"]:
            msg = test_msg_map.get((fail["suite"], fail["test"]), "")
            failures.append({
                "suite": fail["suite"],
                "test": fail["test"],
                "message": msg[:220] if msg else "",
            })
    except Exception:
        suites_dict: dict[str, dict] = {}
        snapshot_tests = []
        for snap in getattr(latest, "tests", []):
            s_name = snap.get("suite_name", "Geral")
            st_val = snap.get("status", "PASS")
            el = float(snap.get("elapsed_s", 0.0))
            t_name = snap.get("test_name", "")
            if s_name not in suites_dict:
                suites_dict[s_name] = {"name": s_name, "total": 0, "passed": 0, "failed": 0, "skipped": 0}
            suites_dict[s_name]["total"] += 1
            if st_val == "PASS":
                suites_dict[s_name]["passed"] += 1
            elif st_val == "FAIL":
                suites_dict[s_name]["failed"] += 1
                failures.append({"suite": s_name, "test": t_name, "message": ""})
            else:
                suites_dict[s_name]["skipped"] += 1
            snapshot_tests.append({"name": t_name, "suite": s_name, "elapsed_s": el})
        suites = list(suites_dict.values())
        slowest = sorted(snapshot_tests, key=lambda t: t["elapsed_s"], reverse=True)[:10]

    history_items = [
        {
            "timestamp": h.timestamp[:19].replace("T", " "),
            "version": h.system_version or h.version,
            "total": h.total,
            "passed": h.passed,
            "failed": h.failed,
            "pass_rate": h.pass_rate,
            "elapsed_s": h.elapsed_s,
        }
        for h in reversed(history[-10:])
    ]

    return {
        "id": system_id,
        "name": str(metadata.get("name", system_id)),
        "version": latest.system_version or latest.version,
        "date": latest.timestamp[:19].replace("T", " "),
        "stats": {
            "total": latest.total,
            "passed": latest.passed,
            "failed": latest.failed,
            "skipped": latest.skipped,
            "pass_rate": latest.pass_rate,
            "elapsed_s": latest.elapsed_s,
        },
        "suites": suites,
        "failures": failures,
        "history": history_items,
        "slowest": slowest,
    }


def collect_systems_data(
    store: SQLiteStore, system_ids: list[str] | None = None
) -> list[dict]:
    """Coleta dados de um ou mais sistemas para geração do relatório PDF."""
    if system_ids:
        ids_to_fetch = [s.strip() for s in system_ids if s.strip()]
    else:
        ids_to_fetch = [m["id"] for m, hist, _ in store.systems() if hist]

    results = []
    for s_id in ids_to_fetch:
        try:
            results.append(collect_system_data(store, s_id))
        except ValueError:
            continue
    return results


def render_custom_pdf(
    systems: list[dict],
    output_path: Path | str,
    title: str = "Relatório de Testes Automatizados",
    sections: list[str] | None = None,
) -> Path:
    """Gera um PDF customizável para 1 ou múltiplos sistemas selecionados."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        CondPageBreak,
        Flowable,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _init_fonts()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if sections is None:
        sections = ["executive", "distribution", "suites", "failures", "history", "slowest"]
    else:
        sections = [s.strip().lower() for s in sections]

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

    styles = getSampleStyleSheet()
    body = ParagraphStyle("CustomBody", parent=styles["BodyText"], fontName="SummaryVera",
                          fontSize=8.5, leading=13, textColor=ink, splitLongWords=True)
    small = ParagraphStyle("CustomSmall", parent=body, fontSize=7.5, leading=11)
    quiet = ParagraphStyle("CustomQuiet", parent=small, textColor=muted)
    eyebrow = ParagraphStyle("CustomEyebrow", parent=small, fontName="SummaryVeraBold",
                             textColor=colors.HexColor("#A9E0C2"), spaceAfter=8)
    hero_title = ParagraphStyle("CustomHeroTitle", parent=body, fontName="SummaryVeraBold",
                                fontSize=16, leading=21, textColor=white, spaceAfter=8)
    hero_meta = ParagraphStyle("CustomHeroMeta", parent=small, textColor=colors.HexColor("#D8EDE3"))
    system_header_title = ParagraphStyle("CustomSysHeaderTitle", parent=body, fontName="SummaryVeraBold",
                                         fontSize=13, leading=18, textColor=white, spaceAfter=4)
    heading = ParagraphStyle("CustomHeading", parent=body, fontName="SummaryVeraBold", fontSize=11,
                             leading=16, spaceBefore=16, spaceAfter=8)
    card_label = ParagraphStyle("CustomCardLabel", parent=small, textColor=muted, spaceAfter=6)
    card_value = ParagraphStyle("CustomCardValue", parent=body, fontName="SummaryVeraBold",
                                fontSize=16, leading=19)
    table_head = ParagraphStyle("CustomTableHead", parent=small, fontName="SummaryVeraBold",
                                textColor=muted)
    failure_title = ParagraphStyle("CustomFailureTitle", parent=body, fontName="SummaryVeraBold",
                                   fontSize=8.5, leading=13, spaceAfter=3)

    def metric_card(label, value, tint, value_color=ink):
        value_style = ParagraphStyle("Val" + label, parent=card_value, textColor=value_color)
        card = Table([[Paragraph(label, card_label)], [Paragraph(escape(str(value)), value_style)]],
                     colWidths=[(content_width - 18) / 3 - 20])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), tint),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
        ]))
        return card

    story = []

    # Se houver múltiplos sistemas, cria a Visão Consolidada inicial
    if len(systems) > 1:
        total_scenarios = sum(s["stats"]["total"] for s in systems)
        total_passed = sum(s["stats"]["passed"] for s in systems)
        total_failed = sum(s["stats"]["failed"] for s in systems)
        total_skipped = sum(s["stats"]["skipped"] for s in systems)
        avg_pass_rate = round((total_passed / total_scenarios * 100) if total_scenarios else 0.0, 1)
        total_elapsed = sum(s["stats"]["elapsed_s"] for s in systems)

        status_label = "COM FALHAS" if total_failed > 0 else "TODOS APROVADOS"
        status_color = "#FFD4CE" if total_failed > 0 else "#BDF0CE"

        hero_cells = [
            Paragraph("ROBOT REPORTS  /  RELATÓRIO CONSOLIDADO", eyebrow),
            Paragraph(escape(title), hero_title),
            Paragraph(f"<font color='{status_color}'><b>{status_label}</b></font> &nbsp;&nbsp;|&nbsp;&nbsp; "
                      f"{len(systems)} sistemas analisados &nbsp;&nbsp;|&nbsp;&nbsp; "
                      f"Total: {total_scenarios} cenários", hero_meta),
        ]
        hero = Table([[hero_cells]], colWidths=[content_width], hAlign="LEFT")
        hero.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ink),
            ("LEFTPADDING", (0, 0), (-1, -1), 18), ("RIGHTPADDING", (0, 0), (-1, -1), 18),
            ("TOPPADDING", (0, 0), (-1, -1), 16), ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ]))
        story.append(hero)

        story.append(Paragraph("Visão executiva consolidada", heading))
        card_w = (content_width - 18) / 3
        card_specs_agg = [
            ("CENÁRIOS TOTAIS", total_scenarios, pale, ink),
            ("TOTAL PASSOU", total_passed, green_soft, green),
            ("TOTAL FALHOU", total_failed, red_soft, red if total_failed else muted),
            ("IGNORADOS", total_skipped, colors.HexColor("#FFF8E9"), amber),
            ("TAXA GLOBAL", f"{avg_pass_rate:.1f}%", pale, ink),
            ("TEMPO TOTAL", f"{total_elapsed:.1f}s", pale, ink),
        ]
        grid_agg = Table([
            [metric_card(*card_specs_agg[0]), "", metric_card(*card_specs_agg[1]), "", metric_card(*card_specs_agg[2])],
            ["", "", "", "", ""],
            [metric_card(*card_specs_agg[3]), "", metric_card(*card_specs_agg[4]), "", metric_card(*card_specs_agg[5])],
        ], colWidths=[card_w, 9, card_w, 9, card_w], rowHeights=[None, 9, None], hAlign="LEFT")
        grid_agg.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.extend([grid_agg, Spacer(1, 14)])

        story.append(Paragraph("Comparativo entre sistemas", heading))
        rows_comp = [[
            Paragraph("SISTEMA", table_head),
            Paragraph("VERSÃO", table_head),
            Paragraph("DATA", table_head),
            Paragraph("TOTAL", table_head),
            Paragraph("PASS", table_head),
            Paragraph("FAIL", table_head),
            Paragraph("TAXA", table_head),
            Paragraph("TEMPO", table_head),
        ]]
        for sys_item in systems:
            st = sys_item["stats"]
            rate_color = red if st["failed"] > 0 else green
            rate_text = f"<font color='{rate_color}'><b>{float(st['pass_rate']):.1f}%</b></font>"
            rows_comp.append([
                Paragraph(escape(str(sys_item["name"])), small),
                Paragraph(escape(str(sys_item.get("version", "-"))), small),
                Paragraph(escape(str(sys_item.get("date", "-"))[:10]), small),
                Paragraph(str(st["total"]), small),
                Paragraph(str(st["passed"]), small),
                Paragraph(str(st["failed"]), small),
                Paragraph(rate_text, small),
                Paragraph(f"{float(st['elapsed_s']):.1f}s", small),
            ])
        rows_comp.append([
            Paragraph("<b>Total acumulado</b>", small),
            Paragraph("-", small),
            Paragraph("-", small),
            Paragraph(f"<b>{total_scenarios}</b>", small),
            Paragraph(f"<b>{total_passed}</b>", small),
            Paragraph(f"<b>{total_failed}</b>", small),
            Paragraph(f"<b>{avg_pass_rate:.1f}%</b>", small),
            Paragraph(f"<b>{total_elapsed:.1f}s</b>", small),
        ])
        comp_table = Table(rows_comp, colWidths=[130, 65, 75, 45, 45, 45, 50, 48], repeatRows=1, hAlign="LEFT")
        comp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), green_soft),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [white, pale]),
            ("BACKGROUND", (0, -1), (-1, -1), line),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, line),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(comp_table)
        story.append(PageBreak())

    # Detalhamento de cada sistema individual
    for index, sys_item in enumerate(systems):
        st = sys_item["stats"]
        name = sys_item["name"]
        date = sys_item.get("date", "-")
        version = sys_item.get("version", "-")
        has_failures = st.get("failed", 0) > 0
        sys_status_label = "COM FALHAS" if has_failures else "SEM FALHAS"
        sys_status_color = "#FFD4CE" if has_failures else "#BDF0CE"

        if len(systems) == 1:
            hero_cells = [
                Paragraph("ROBOT REPORTS  /  RESUMO EXECUTIVO", eyebrow),
                Paragraph(f"{escape(title)} — {escape(name)}", hero_title),
                Paragraph(f"<font color='{sys_status_color}'><b>{sys_status_label}</b></font> &nbsp;&nbsp;|&nbsp;&nbsp; "
                          f"Versão: {escape(version)} &nbsp;&nbsp;|&nbsp;&nbsp; {escape(date)}", hero_meta),
            ]
            hero = Table([[hero_cells]], colWidths=[content_width], hAlign="LEFT")
            hero.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), ink),
                ("LEFTPADDING", (0, 0), (-1, -1), 18), ("RIGHTPADDING", (0, 0), (-1, -1), 18),
                ("TOPPADDING", (0, 0), (-1, -1), 16), ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
            ]))
            story.append(hero)
        else:
            banner = Table([[[
                Paragraph(f"SISTEMA: {escape(name).upper()}", system_header_title),
                Paragraph(f"<font color='{sys_status_color}'><b>{sys_status_label}</b></font> &nbsp;&nbsp;|&nbsp;&nbsp; "
                          f"Versão: {escape(version)} &nbsp;&nbsp;|&nbsp;&nbsp; Data: {escape(date)}", hero_meta),
            ]]], colWidths=[content_width], hAlign="LEFT")
            banner.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), ink),
                ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(banner)

        if "executive" in sections:
            story.append(Paragraph("Visão executiva", heading))
            card_specs = [
                ("CENÁRIOS", st["total"], pale, ink),
                ("PASSOU", st["passed"], green_soft, green),
                ("FALHOU", st["failed"], red_soft, red if st["failed"] else muted),
                ("IGNORADO", st["skipped"], colors.HexColor("#FFF8E9"), amber),
                ("SUCESSO", f'{float(st["pass_rate"]):.1f}%', pale, ink),
                ("DURAÇÃO", f'{float(st["elapsed_s"]):.1f}s', pale, ink),
            ]
            card_w = (content_width - 18) / 3
            grid = Table([
                [metric_card(*card_specs[0]), "", metric_card(*card_specs[1]), "", metric_card(*card_specs[2])],
                ["", "", "", "", ""],
                [metric_card(*card_specs[3]), "", metric_card(*card_specs[4]), "", metric_card(*card_specs[5])],
            ], colWidths=[card_w, 9, card_w, 9, card_w], rowHeights=[None, 9, None], hAlign="LEFT")
            grid.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.extend([grid, Spacer(1, 10)])

        if "distribution" in sections:
            story.extend([
                Paragraph("Distribuição dos resultados", small),
                Spacer(1, 5),
                DistributionBar(st, content_width, 10),
                Spacer(1, 6),
                Table([[
                    LegendItem("Passou", st["passed"], green),
                    LegendItem("Falhou", st["failed"], red),
                    LegendItem("Ignorado", st["skipped"], amber),
                ]], colWidths=[content_width / 3] * 3, hAlign="LEFT",
                style=[("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]),
                Spacer(1, 12),
            ])

        if "suites" in sections:
            story.extend([CondPageBreak(90), Paragraph("Resumo por suíte", heading)])
            if sys_item.get("suites"):
                rows = [[Paragraph(text, table_head) for text in ("SUÍTE", "DISTRIBUIÇÃO", "TOTAL", "PASS", "FAIL")]]
                for suite in sys_item["suites"]:
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
                    ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(table)
            else:
                story.append(Paragraph("Nenhuma suíte detalhada para este sistema.", quiet))
            story.append(Spacer(1, 10))

        if "failures" in sections:
            story.extend([CondPageBreak(90), Paragraph("Testes com falha", heading)])
            if sys_item.get("failures"):
                for failure in sys_item["failures"]:
                    msg = failure.get("message")
                    cell_content = [
                        Paragraph(escape(str(failure["test"])), failure_title),
                        Paragraph(escape(str(failure["suite"])), quiet),
                    ]
                    if msg:
                        cell_content.append(Paragraph(f"<font color='{red}'>{escape(str(msg)[:220])}</font>", small))
                    failure_card = Table([[cell_content]], colWidths=[content_width], hAlign="LEFT")
                    failure_card.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, -1), red_soft),
                        ("LINEBEFORE", (0, 0), (0, -1), 3, red),
                        ("LEFTPADDING", (0, 0), (-1, -1), 11),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]))
                    story.append(KeepTogether([failure_card, Spacer(1, 6)]))
            else:
                no_failures = Table([[Paragraph("Nenhum teste com falha nesta execução.", body)]],
                                    colWidths=[content_width], hAlign="LEFT")
                no_failures.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), green_soft),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, green),
                    ("LEFTPADDING", (0, 0), (-1, -1), 11),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]))
                story.append(no_failures)
            story.append(Spacer(1, 10))

        if "slowest" in sections and sys_item.get("slowest"):
            story.extend([CondPageBreak(90), Paragraph("Testes mais lentos (Top 10)", heading)])
            slow_rows = [[Paragraph(text, table_head) for text in ("CENÁRIO / TESTE", "SUÍTE", "DURAÇÃO")]]
            for slow in sys_item["slowest"]:
                test_name = slow.get("name") or slow.get("test", "")
                slow_rows.append([
                    Paragraph(escape(str(test_name)), small),
                    Paragraph(escape(str(slow.get("suite", "-"))), small),
                    Paragraph(f"{float(slow.get('elapsed_s', 0)):.2f}s", small),
                ])
            slow_table = Table(slow_rows, colWidths=[260, 180, 63], repeatRows=1, hAlign="LEFT")
            slow_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), pale),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, pale]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, line),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.extend([slow_table, Spacer(1, 10)])

        if "history" in sections and sys_item.get("history"):
            story.extend([CondPageBreak(90), Paragraph("Histórico de execuções recentes", heading)])
            hist_rows = [[Paragraph(text, table_head) for text in ("DATA / HORA", "VERSÃO", "TOTAL", "PASSOU", "FALHOU", "TAXA")]]
            for h in sys_item["history"][:8]:
                h_failed = h.get("failed", 0)
                h_rate = float(h.get("pass_rate", 0))
                rate_color = red if h_failed > 0 else green
                hist_rows.append([
                    Paragraph(escape(str(h.get("timestamp", "-"))), small),
                    Paragraph(escape(str(h.get("version", "-"))), small),
                    Paragraph(str(h.get("total", 0)), small),
                    Paragraph(str(h.get("passed", 0)), small),
                    Paragraph(str(h_failed), small),
                    Paragraph(f"<font color='{rate_color}'><b>{h_rate:.1f}%</b></font>", small),
                ])
            hist_table = Table(hist_rows, colWidths=[120, 100, 70, 70, 70, 73], repeatRows=1, hAlign="LEFT")
            hist_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), green_soft),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, pale]),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, line),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.extend([hist_table, Spacer(1, 10)])

        if index < len(systems) - 1:
            story.append(PageBreak())

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(doc.leftMargin, 38, A4[0] - doc.rightMargin, 38)
        canvas.setFont("SummaryVera", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(doc.leftMargin, 25, "ROBOT REPORTS  /  RELATÓRIO EXECUTIVO CUSTOMIZADO")
        canvas.drawRightString(A4[0] - doc.rightMargin, 25, f"Página {doc.page}")
        canvas.restoreState()

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output_path.parent, prefix=f".{output_path.stem}.",
                                         suffix=".pdf", delete=False) as stream:
            temporary = Path(stream.name)
        document = SimpleDocTemplate(str(temporary), pagesize=A4, leftMargin=46, rightMargin=46,
                                     topMargin=38, bottomMargin=50, title=str(title))
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        os.replace(temporary, output_path)
        return output_path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

