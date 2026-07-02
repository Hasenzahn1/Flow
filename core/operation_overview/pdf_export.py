import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Constants ─────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm

TRIAGE_COLORS = {
    0: colors.HexColor("#9e9e9e"),
    1: colors.HexColor("#4caf50"),
    2: colors.HexColor("#ffc107"),
    3: colors.HexColor("#f44336"),
}
TRIAGE_LABELS = {0: "Unbekannt", 1: "Grün", 2: "Gelb", 3: "Rot"}
STATUS_LABELS = {0: "Neu", 1: "In Bearbeitung", 2: "Abgeschlossen"}

MISSION_HEADER_BG = colors.HexColor("#2c3e50")
MISSION_HEADER_FG = colors.white
ROW_ALT = colors.HexColor("#f5f5f5")

# ── Styles ────────────────────────────────────────────────────────────────────

_base = getSampleStyleSheet()


def _styles():
    return {
        "normal": ParagraphStyle("normal", fontName="Helvetica", fontSize=9,
                                 leading=13, spaceAfter=0),
        "bold": ParagraphStyle("bold", fontName="Helvetica-Bold", fontSize=9,
                               leading=13),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8,
                                leading=11, textColor=colors.HexColor("#555")),
        "cover_title": ParagraphStyle("cover_title", fontName="Helvetica-Bold",
                                      fontSize=16, leading=20, spaceAfter=4),
        "cover_meta": ParagraphStyle("cover_meta", fontName="Helvetica",
                                     fontSize=10, leading=14),
        "section_heading": ParagraphStyle("section_heading",
                                          fontName="Helvetica-Bold", fontSize=11,
                                          leading=16, spaceBefore=10,
                                          spaceAfter=4,
                                          textColor=colors.HexColor("#2c3e50")),
        "description": ParagraphStyle("description", fontName="Helvetica",
                                      fontSize=8.5, leading=12,
                                      textColor=colors.HexColor("#333")),
        "italic": ParagraphStyle("italic", fontName="Helvetica-Oblique",
                                 fontSize=8.5, leading=12,
                                 textColor=colors.HexColor("#888")),
        "mission_header": ParagraphStyle("mission_header",
                                         fontName="Helvetica-Bold", fontSize=9,
                                         leading=13, textColor=MISSION_HEADER_FG),
        "table_header": ParagraphStyle("table_header", fontName="Helvetica-Bold",
                                       fontSize=8, leading=11),
        "table_cell": ParagraphStyle("table_cell", fontName="Helvetica",
                                     fontSize=8, leading=11),
        "triage_cell": ParagraphStyle("triage_cell", fontName="Helvetica-Bold",
                                      fontSize=8, leading=11),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_date(unix_ts):
    if not unix_ts:
        return "—"
    return datetime.datetime.fromtimestamp(unix_ts).strftime("%d.%m.%Y")


def _fmt_datetime(unix_ts):
    if not unix_ts:
        return "—"
    return datetime.datetime.fromtimestamp(unix_ts).strftime("%d.%m.%Y %H:%M")


def _fmt_time(unix_ts):
    if not unix_ts:
        return "—"
    return datetime.datetime.fromtimestamp(unix_ts).strftime("%H:%M")


def _escape(text):
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


# ── Header / Footer ───────────────────────────────────────────────────────────

def _make_header_footer(op_name: str, export_ts: str):
    def _draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(colors.HexColor("#2c3e50"))
        canvas.drawString(MARGIN, PAGE_H - MARGIN + 4, "FLOW — Lageprotokoll")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#555"))
        canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - MARGIN + 4,
                               f"Exportiert am: {export_ts}")
        canvas.setStrokeColor(colors.HexColor("#ccc"))
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, PAGE_H - MARGIN + 1, PAGE_W - MARGIN,
                    PAGE_H - MARGIN + 1)
        # Footer
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#888"))
        canvas.drawString(MARGIN, MARGIN - 6, _escape(op_name))
        canvas.drawRightString(PAGE_W - MARGIN, MARGIN - 6,
                               f"Seite {doc.page}")
        canvas.restoreState()
    return _draw


# ── Cover block ───────────────────────────────────────────────────────────────

def _cover_block(operation: dict, styles: dict) -> list:
    total_missions = len(operation.get("missions", []))
    total_persons = sum(
        len(m.get("persons", [])) for m in operation.get("missions", [])
    )
    name = _escape(operation.get("name", "—"))
    date = _fmt_date(operation.get("date"))
    place = _escape(operation.get("place") or "—")
    desc = _escape(operation.get("description") or "")

    content_w = PAGE_W - 2 * MARGIN
    data = [
        [Paragraph(f"LAGE: {name}", styles["cover_title"])],
        [Paragraph(f"Datum: {date} &nbsp;&nbsp;|&nbsp;&nbsp; Ort: {place}", styles["cover_meta"])],
    ]
    if desc:
        data.append([Paragraph(f"Beschreibung: {desc}", styles["cover_meta"])])
    data.append([Paragraph(
        f"Gesamt: <b>{total_missions}</b> Einsätze &nbsp;|&nbsp; <b>{total_persons}</b> Patienten",
        styles["cover_meta"]
    )])

    table = Table(data, colWidths=[content_w])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#2c3e50")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 10),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf0f8")),
    ]))
    return [table, Spacer(1, 8 * mm)]


# ── Person table ──────────────────────────────────────────────────────────────

def _person_table(persons: list, styles: dict) -> Table:
    headers = ["#", "Nachname", "Vorname", "Geb.", "Geschlecht",
               "Verletzt", "Triage", "Übergabe", "Info"]
    col_widths = [8*mm, 22*mm, 22*mm, 20*mm, 20*mm,
                  14*mm, 22*mm, 25*mm, None]
    # Last column fills remaining space
    fixed = sum(w for w in col_widths if w)
    available = PAGE_W - 2 * MARGIN
    col_widths[-1] = available - fixed

    header_row = [Paragraph(h, styles["table_header"]) for h in headers]
    rows = [header_row]

    for p in persons:
        triage = p.get("triage", 0)
        tc = TRIAGE_COLORS.get(triage, colors.lightgrey)
        triage_para = Paragraph(
            f'<font color="#{tc.hexval()[2:]}">■</font> {TRIAGE_LABELS.get(triage, "—")}',
            styles["triage_cell"]
        )
        rows.append([
            Paragraph(str(p.get("number", "")), styles["table_cell"]),
            Paragraph(_escape(p.get("last_name") or "—"), styles["table_cell"]),
            Paragraph(_escape(p.get("name") or "—"), styles["table_cell"]),
            Paragraph(_fmt_date(p.get("birthdate")), styles["table_cell"]),
            Paragraph(_escape(p.get("gender") or "—"), styles["table_cell"]),
            Paragraph("Ja" if p.get("hurt") else "Nein", styles["table_cell"]),
            triage_para,
            Paragraph(_escape(p.get("handover") or "—"), styles["table_cell"]),
            Paragraph(_escape(p.get("info") or ""), styles["table_cell"]),
        ])

    style_cmds = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce6f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#ccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style_cmds))
    return table


# ── Mission block ─────────────────────────────────────────────────────────────

def _mission_block(mission: dict, styles: dict) -> list:
    number = mission.get("number", "?")
    status = STATUS_LABELS.get(mission.get("status", 0), "—")
    place = _escape(mission.get("place") or "—")
    unit = _escape(mission.get("unit") or "—")
    persons = mission.get("persons", [])
    n_pat = len(persons)
    changed = _fmt_time(mission.get("changed_at"))
    description = _escape(mission.get("description") or "")

    content_w = PAGE_W - 2 * MARGIN
    header_text = (
        f"#{number} &nbsp;&nbsp;|&nbsp;&nbsp; {status} &nbsp;&nbsp;|"
        f"&nbsp;&nbsp; Ort: {place} &nbsp;&nbsp;|"
        f"&nbsp;&nbsp; Einheit: {unit} &nbsp;&nbsp;|"
        f"&nbsp;&nbsp; {n_pat} Pat. &nbsp;&nbsp;|"
        f"&nbsp;&nbsp; Geändert: {changed}"
    )
    header_table = Table(
        [[Paragraph(header_text, styles["mission_header"])]],
        colWidths=[content_w],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MISSION_HEADER_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    block = [header_table]

    if description:
        desc_table = Table(
            [[Paragraph(f"<b>Beschreibung:</b> {description}", styles["description"])]],
            colWidths=[content_w],
        )
        desc_table.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f8f8")),
            ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#ccc")),
        ]))
        block.append(desc_table)

    if persons:
        block.append(Spacer(1, 2 * mm))
        block.append(_person_table(persons, styles))
    else:
        no_pat = Table(
            [[Paragraph("Keine Patienten", styles["italic"])]],
            colWidths=[content_w],
        )
        no_pat.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        block.append(no_pat)

    block.append(Spacer(1, 5 * mm))
    return block


# ── Public API ────────────────────────────────────────────────────────────────

def generate_operation_pdf(operation: dict) -> bytes:
    """Return PDF bytes for the given operation dict (with nested missions+persons)."""
    buf = BytesIO()
    export_ts = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    op_name = operation.get("name", "Unbekannte Lage")
    styles = _styles()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 6 * mm,
        bottomMargin=MARGIN + 6 * mm,
    )

    story = []
    story += _cover_block(operation, styles)

    missions = operation.get("missions", [])
    current = [m for m in missions if m.get("status", 0) in (0, 1)]
    finished = [m for m in missions if m.get("status", 0) == 2]

    if current:
        story.append(Paragraph(f"Aktuelle Einsätze ({len(current)})",
                                styles["section_heading"]))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#2c3e50"), spaceAfter=4))
        for m in current:
            story += _mission_block(m, styles)

    if finished:
        story.append(Paragraph(f"Abgeschlossene Einsätze ({len(finished)})",
                                styles["section_heading"]))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#2c3e50"), spaceAfter=4))
        for m in finished:
            story += _mission_block(m, styles)

    header_footer = _make_header_footer(op_name, export_ts)
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return buf.getvalue()
