import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    HRFlowable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


PORTRAIT = A4
LANDSCAPE = landscape(A4)
MARGIN = 15 * mm

SECTION_PATIENTS = "patients"
SECTION_HELPERS_SUMMARY = "helpers_summary"
SECTION_HELPERS_DETAIL = "helpers_detail"
SECTION_VEHICLES = "vehicles"
SECTION_ORDER = (
    SECTION_PATIENTS,
    SECTION_HELPERS_SUMMARY,
    SECTION_HELPERS_DETAIL,
    SECTION_VEHICLES,
)
SECTION_ORIENTATION = {
    SECTION_PATIENTS: "portrait",
    SECTION_HELPERS_SUMMARY: "landscape",
    SECTION_HELPERS_DETAIL: "portrait",
    SECTION_VEHICLES: "landscape",
}

TRIAGE_COLORS = {
    0: colors.HexColor("#9e9e9e"),
    1: colors.HexColor("#4caf50"),
    2: colors.HexColor("#ffc107"),
    3: colors.HexColor("#f44336"),
}
TRIAGE_LABELS = {0: "Unbekannt", 1: "Grün", 2: "Gelb", 3: "Rot"}
STATUS_LABELS = {0: "Neu", 1: "In Bearbeitung", 2: "Abgeschlossen"}
GENDER_LABELS = {"m": "Männlich", "w": "Weiblich", "d": "Divers"}
ROLE_LABELS = {"leader": "Gruppenführer", "member": "Besatzung"}

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#1976D2")
PALE_BLUE = colors.HexColor("#EAF3FB")
ROW_ALT = colors.HexColor("#F5F8FA")
BORDER = colors.HexColor("#C9D5DF")
MUTED = colors.HexColor("#526575")


def _styles():
    return {
        "normal": ParagraphStyle(
            "normal", fontName="Helvetica", fontSize=8.5, leading=12
        ),
        "small": ParagraphStyle(
            "small", fontName="Helvetica", fontSize=7.5, leading=10, textColor=MUTED
        ),
        "title": ParagraphStyle(
            "title", fontName="Helvetica-Bold", fontSize=17, leading=21,
            textColor=NAVY, spaceAfter=3,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="Helvetica", fontSize=9.5, leading=13,
            textColor=MUTED,
        ),
        "section": ParagraphStyle(
            "section", fontName="Helvetica-Bold", fontSize=11, leading=15,
            textColor=NAVY, spaceBefore=7, spaceAfter=4,
        ),
        "group": ParagraphStyle(
            "group", fontName="Helvetica-Bold", fontSize=12, leading=16,
            textColor=NAVY, spaceBefore=5, spaceAfter=5,
        ),
        "table_header": ParagraphStyle(
            "table_header", fontName="Helvetica-Bold", fontSize=7.5, leading=10,
            textColor=NAVY,
        ),
        "table_cell": ParagraphStyle(
            "table_cell", fontName="Helvetica", fontSize=7.5, leading=10,
        ),
        "white_header": ParagraphStyle(
            "white_header", fontName="Helvetica-Bold", fontSize=9, leading=12,
            textColor=colors.white,
        ),
        "card_label": ParagraphStyle(
            "card_label", fontName="Helvetica-Bold", fontSize=6.2, leading=7.5,
            textColor=MUTED,
        ),
        "card_value": ParagraphStyle(
            "card_value", fontName="Helvetica", fontSize=6.8, leading=8.3,
        ),
        "empty": ParagraphStyle(
            "empty", fontName="Helvetica-Oblique", fontSize=8.5, leading=12,
            textColor=colors.HexColor("#6D7D8A"), leftIndent=5,
        ),
    }


def _escape(value):
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _display(value, fallback="-"):
    text = str(value).strip() if value is not None else ""
    return _escape(text) if text else fallback


def _fmt_date(unix_ts):
    if not unix_ts:
        return "-"
    return datetime.datetime.fromtimestamp(unix_ts).strftime("%d.%m.%Y")


def _fmt_datetime(unix_ts):
    if not unix_ts:
        return "-"
    return datetime.datetime.fromtimestamp(unix_ts).strftime("%d.%m.%Y %H:%M")


def _fmt_time(unix_ts):
    if not unix_ts:
        return "-"
    return datetime.datetime.fromtimestamp(unix_ts).strftime("%H:%M")


def _fmt_iso_datetime(value):
    if not value:
        return "-"
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return _display(value)
    return parsed.strftime("%d.%m.%Y %H:%M")


def _fmt_iso_date(value):
    if not value:
        return None
    try:
        parsed = datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%d.%m.%Y")


def _page_frame(page_size):
    width, height = page_size
    return Frame(
        MARGIN,
        MARGIN + 6 * mm,
        width - 2 * MARGIN,
        height - 2 * MARGIN - 12 * mm,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )


def _draw_header_footer(operation_name, export_ts):
    def draw(canvas, doc):
        width, height = canvas._pagesize
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(NAVY)
        canvas.drawString(MARGIN, height - MARGIN + 4, "FLOW - Lageexport")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(
            width - MARGIN, height - MARGIN + 4, f"Exportiert am: {export_ts}"
        )
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, height - MARGIN + 1, width - MARGIN, height - MARGIN + 1)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#71808D"))
        canvas.drawString(MARGIN, MARGIN - 6, str(operation_name or "Unbekannte Lage"))
        canvas.drawRightString(width - MARGIN, MARGIN - 6, f"Seite {doc.page}")
        canvas.restoreState()

    return draw


def _build_doc(buffer, first_orientation, operation_name, export_ts):
    first_size = PORTRAIT if first_orientation == "portrait" else LANDSCAPE
    on_page = _draw_header_footer(operation_name, export_ts)
    doc = BaseDocTemplate(
        buffer,
        pagesize=first_size,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 6 * mm,
        bottomMargin=MARGIN + 6 * mm,
        title=f"FLOW Lageexport - {operation_name}",
        author="FLOW",
    )
    doc.addPageTemplates([
        PageTemplate(
            id="first", pagesize=first_size, frames=[_page_frame(first_size)], onPage=on_page
        ),
        PageTemplate(
            id="portrait", pagesize=PORTRAIT, frames=[_page_frame(PORTRAIT)], onPage=on_page
        ),
        PageTemplate(
            id="landscape", pagesize=LANDSCAPE,
            frames=[_page_frame(LANDSCAPE)], onPage=on_page,
        ),
    ])
    return doc


def _section_title(title, operation, styles, description=None):
    name = _display(operation.get("name"))
    date = _fmt_date(operation.get("date"))
    place = _display(operation.get("place"))
    flowables = [
        Paragraph(title, styles["title"]),
        Paragraph(
            f"Lage: <b>{name}</b> &nbsp;|&nbsp; Datum: {date} &nbsp;|&nbsp; Ort: {place}",
            styles["subtitle"],
        ),
    ]
    if description:
        flowables.append(Paragraph(_escape(description), styles["subtitle"]))
    flowables.extend([
        Spacer(1, 3 * mm),
        HRFlowable(width="100%", thickness=0.8, color=BLUE, spaceAfter=5 * mm),
    ])
    return flowables


def _standard_table(rows, col_widths, repeat_rows=1, small=False):
    table = Table(rows, colWidths=col_widths, repeatRows=repeat_rows, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3 if small else 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 if small else 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _metric_table(metrics, styles, page_width):
    width = page_width - 2 * MARGIN
    cells = []
    for label, value in metrics:
        cells.append(Paragraph(
            f'<font size="7" color="#526575">{_escape(label)}</font><br/>'
            f'<font size="13"><b>{_escape(value)}</b></font>',
            styles["normal"],
        ))
    table = Table([cells], colWidths=[width / len(cells)] * len(cells))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F7FB")),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _patient_table(persons, styles):
    headers = ["#", "Nachname", "Vorname", "Geb.", "Geschlecht", "Verletzt", "Triage", "Übergabe", "Info"]
    widths = [8*mm, 22*mm, 22*mm, 19*mm, 19*mm, 14*mm, 21*mm, 24*mm, 31*mm]
    rows = [[Paragraph(h, styles["table_header"]) for h in headers]]
    for person in persons:
        triage = person.get("triage", 0)
        triage_color = TRIAGE_COLORS.get(triage, colors.lightgrey).hexval()
        rows.append([
            Paragraph(_display(person.get("number")), styles["table_cell"]),
            Paragraph(_display(person.get("last_name")), styles["table_cell"]),
            Paragraph(_display(person.get("name")), styles["table_cell"]),
            Paragraph(_fmt_date(person.get("birthdate")), styles["table_cell"]),
            Paragraph(_display(person.get("gender")), styles["table_cell"]),
            Paragraph("Ja" if person.get("hurt") else "Nein", styles["table_cell"]),
            Paragraph(
                f'<font color="{triage_color}"><b>{_escape(TRIAGE_LABELS.get(triage, "-"))}</b></font>',
                styles["table_cell"],
            ),
            Paragraph(_display(person.get("handover")), styles["table_cell"]),
            Paragraph(_display(person.get("info")), styles["table_cell"]),
        ])
    return _standard_table(rows, widths)


def _mission_block(mission, styles):
    persons = mission.get("persons", [])
    header_text = (
        f"#{_display(mission.get('number'))} &nbsp;|&nbsp; "
        f"{_escape(STATUS_LABELS.get(mission.get('status', 0), '-'))} &nbsp;|&nbsp; "
        f"Ort: {_display(mission.get('place'))} &nbsp;|&nbsp; "
        f"Einheit: {_display(mission.get('unit'))} &nbsp;|&nbsp; "
        f"{len(persons)} Pat. &nbsp;|&nbsp; Geändert: {_fmt_time(mission.get('changed_at'))}"
    )
    header = Table([[Paragraph(header_text, styles["white_header"])]], colWidths=[180 * mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    block = [CondPageBreak(34 * mm), header]
    if mission.get("description"):
        description = Table([[
            Paragraph(
                f"<b>Beschreibung:</b> {_escape(mission['description'])}", styles["normal"]
            )
        ]], colWidths=[180 * mm])
        description.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFB")),
            ("BOX", (0, 0), (-1, -1), 0.35, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        block.append(description)
    block.append(Spacer(1, 2 * mm))
    block.append(_patient_table(persons, styles) if persons else Paragraph("Keine Patienten", styles["empty"]))
    block.append(Spacer(1, 5 * mm))
    return block


def _patient_section(operation, styles):
    missions = operation.get("missions", [])
    patient_count = sum(len(mission.get("persons", [])) for mission in missions)
    story = _section_title("Patientenübersicht", operation, styles, operation.get("description"))
    story.append(_metric_table([
        ("Einsätze", str(len(missions))),
        ("Patienten", str(patient_count)),
        ("Aktuelle Einsätze", str(sum(m.get("status", 0) in (0, 1) for m in missions))),
    ], styles, PORTRAIT[0]))
    story.append(Spacer(1, 4 * mm))
    groups = (
        ("Aktuelle Einsätze", [m for m in missions if m.get("status", 0) in (0, 1)]),
        ("Abgeschlossene Einsätze", [m for m in missions if m.get("status", 0) == 2]),
    )
    has_content = False
    for title, group in groups:
        if not group:
            continue
        has_content = True
        story.append(Paragraph(f"{title} ({len(group)})", styles["section"]))
        for mission in group:
            story.extend(_mission_block(mission, styles))
    if not has_content:
        story.append(Paragraph("Keine Einsätze vorhanden.", styles["empty"]))
    return story


def _helper_name(helper):
    return " ".join(part for part in (helper.get("first_name"), helper.get("last_name")) if part) or "-"


def _helper_sort_key(helper):
    return (
        (helper.get("last_name") or "").casefold(),
        (helper.get("first_name") or "").casefold(),
    )


def _helper_groups(helpers):
    items = sorted(helpers.get("items", []), key=_helper_sort_key)
    return (
        [item for item in items if item.get("status") == "Anwesend"],
        [item for item in items if item.get("status") == "Abgemeldet"],
    )


def _helper_metrics(helpers, styles, page_width):
    stats = helpers.get("stats", {})
    status = stats.get("status", {})
    gender = stats.get("gender", {})
    nutrition = stats.get("nutrition", {})
    present = status.get("Anwesend", 0)
    nutrition_known = sum(nutrition.values())
    gender_text = (
        f"M {gender.get('m', 0)} / W {gender.get('w', 0)} / "
        f"D {gender.get('d', 0)} / Ohne {gender.get('none', 0)}"
    )
    nutrition_parts = [f"{name}: {count}" for name, count in nutrition.items() if count]
    nutrition_parts.append(f"Keine Angabe: {max(0, present - nutrition_known)}")
    return _metric_table([
        ("Anwesende Helfer", str(present)),
        ("Geschlecht", gender_text),
        ("Ernährung", " | ".join(nutrition_parts)),
    ], styles, page_width)


def _helper_summary_table(items, styles):
    headers = ["Name", "Qualifikationen", "Fahrzeug", "Geschlecht", "Ernährung", "Telefon", "Einsatzort"]
    widths = [39*mm, 44*mm, 35*mm, 24*mm, 42*mm, 37*mm, 46*mm]
    rows = [[Paragraph(header, styles["table_header"]) for header in headers]]
    for helper in items:
        rows.append([
            Paragraph(_display(_helper_name(helper)), styles["table_cell"]),
            Paragraph(_display(", ".join(helper.get("qualifications", []))), styles["table_cell"]),
            Paragraph(_display(helper.get("vehicle_call_sign")), styles["table_cell"]),
            Paragraph(_display(GENDER_LABELS.get(helper.get("gender"), "Keine Angabe")), styles["table_cell"]),
            Paragraph(_display(helper.get("nutrition_type"), "Keine Angabe"), styles["table_cell"]),
            Paragraph(_display(helper.get("mobile")), styles["table_cell"]),
            Paragraph(_display(helper.get("deployment_location")), styles["table_cell"]),
        ])
    return _standard_table(rows, widths, small=True)


def _helper_group_summary(title, items, styles):
    story = [Paragraph(f"{title} ({len(items)})", styles["group"])]
    if items:
        story.append(_helper_summary_table(items, styles))
    else:
        story.append(Paragraph(f"Keine {title.lower()} vorhanden.", styles["empty"]))
    return story


def _helpers_summary_section(operation, helpers, styles):
    present, absent = _helper_groups(helpers)
    story = _section_title("Helferübersicht", operation, styles)
    story.extend([_helper_metrics(helpers, styles, LANDSCAPE[0]), Spacer(1, 4 * mm)])
    story.extend(_helper_group_summary("Anwesende Helfer", present, styles))
    if absent:
        story.append(PageBreak())
        story.extend(_helper_group_summary("Abgemeldete Helfer", absent, styles))
    return story


def _helper_detail_pairs(helper):
    role = ROLE_LABELS.get(helper.get("vehicle_role"))
    vehicle = helper.get("vehicle_call_sign")
    vehicle_assignment = f"{vehicle} ({role})" if vehicle and role else vehicle
    return [
        ("Nachname", helper.get("last_name")),
        ("Vorname", helper.get("first_name")),
        ("Geburtsdatum", _fmt_iso_date(helper.get("birth_date"))),
        ("Geschlecht", GENDER_LABELS.get(helper.get("gender"), "Keine Angabe")),
        ("Straße", helper.get("street")),
        ("PLZ", helper.get("postal_code")),
        ("Ort", helper.get("city")),
        ("Nationalität", helper.get("nationality")),
        ("Mobilnummer", helper.get("mobile")),
        ("E-Mail", helper.get("email")),
        ("Kreisverband", helper.get("district_association")),
        ("Gemeinschaft", helper.get("community")),
        ("Ernährung", helper.get("nutrition_type") or "Keine Angabe"),
        ("Ern.-Hinweis", helper.get("nutrition_note")),
        ("Qualifikationen", ", ".join(helper.get("qualifications", []))),
        ("Fahrzeug / Rolle", vehicle_assignment),
        ("Einsatzort", helper.get("deployment_location")),
        ("Einsatzbeginn", _fmt_iso_datetime(helper.get("deployment_start")) if helper.get("deployment_start") else None),
        ("Einsatzende", _fmt_iso_datetime(helper.get("deployment_end")) if helper.get("deployment_end") else None),
        ("Einsatzinfo", helper.get("deployment_info")),
        ("Status", helper.get("status")),
        ("Quelle", helper.get("source_display")),
        ("Erfasst am", _fmt_datetime(helper.get("registered_at")) if helper.get("registered_at") else None),
        ("Mitgliedsnummer", helper.get("membership_number")),
        ("KV-Code (Rohwert)", helper.get("district_association_raw")),
        ("Ausweisnummer", helper.get("card_number")),
        ("Prüfcode", helper.get("verification_code")),
    ]


def _helper_detail_card(helper, styles):
    pairs = [
        pair for pair in _helper_detail_pairs(helper)
        if pair[1] is not None and str(pair[1]).strip()
    ]
    rows = [[Paragraph(_display(_helper_name(helper)), styles["white_header"]), "", "", "", "", ""]]
    for index in range(0, len(pairs), 3):
        row = []
        for label, value in pairs[index:index + 3]:
            row.extend([
                Paragraph(_escape(label), styles["card_label"]),
                Paragraph(_display(value), styles["card_value"]),
            ])
        while len(row) < 6:
            row.extend(["", ""])
        rows.append(row)
    table = Table(
        rows,
        colWidths=[21*mm, 39*mm, 21*mm, 39*mm, 21*mm, 39*mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ROW_ALT]),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 1), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 3),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _helper_group_detail(title, items, styles):
    story = [Paragraph(f"{title} ({len(items)})", styles["group"])]
    if not items:
        story.append(Paragraph(f"Keine {title.lower()} vorhanden.", styles["empty"]))
        return story
    for helper in items:
        story.extend([CondPageBreak(38 * mm), _helper_detail_card(helper, styles), Spacer(1, 3 * mm)])
    return story


def _helpers_detail_section(operation, helpers, styles):
    present, absent = _helper_groups(helpers)
    story = _section_title("Detaillierte Helferregistrierung", operation, styles)
    story.extend([_helper_metrics(helpers, styles, PORTRAIT[0]), Spacer(1, 4 * mm)])
    story.extend(_helper_group_detail("Anwesende Helfer", present, styles))
    if absent:
        story.append(PageBreak())
        story.extend(_helper_group_detail("Abgemeldete Helfer", absent, styles))
    return story


def _vehicle_summary(vehicles, styles):
    stats = vehicles.get("stats", {})
    statuses = stats.get("statuses", {})
    status_text = " | ".join(
        f"{name}: {statuses.get(name, 0)}"
        for name in ("Unbesetzt", "Unvollständig", "Gut besetzt", "Voll", "Überbelegt")
    )
    return _metric_table([
        ("Fahrzeuge", str(vehicles.get("total", len(vehicles.get("items", []))))),
        ("Belegte Plätze", f"{stats.get('occupied', 0)} / {stats.get('max_seats', 0)}"),
        ("Statusübersicht", status_text),
    ], styles, LANDSCAPE[0])


def _vehicle_block(vehicle, styles):
    header = Table([[
        Paragraph(
            f"{_display(vehicle.get('call_sign'))} - {_display(vehicle.get('vehicle_type'))}",
            styles["white_header"],
        )
    ]], colWidths=[267 * mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    free = vehicle.get("free_seats", 0)
    capacity_label = f"{free} frei" if free >= 0 else f"{abs(free)} überbelegt"
    meta = _standard_table([[
        Paragraph("<b>Telefon</b><br/>" + _display(vehicle.get("phone")), styles["table_cell"]),
        Paragraph(f"<b>Sollbesetzung</b><br/>{vehicle.get('target_occupancy', 0)}", styles["table_cell"]),
        Paragraph(f"<b>Maximalsitze</b><br/>{vehicle.get('max_seats', 0)}", styles["table_cell"]),
        Paragraph(f"<b>Ist-Besetzung</b><br/>{vehicle.get('crew_count', 0)}", styles["table_cell"]),
        Paragraph(f"<b>Kapazität</b><br/>{_escape(capacity_label)}", styles["table_cell"]),
        Paragraph("<b>Status</b><br/>" + _display(vehicle.get("status")), styles["table_cell"]),
    ]], [44.5 * mm] * 6, repeat_rows=0)
    crew = vehicle.get("crew", [])
    if crew:
        crew_rows = [[
            Paragraph("Name", styles["table_header"]),
            Paragraph("Rolle", styles["table_header"]),
        ]]
        for person in crew:
            crew_rows.append([
                Paragraph(_display(_helper_name(person)), styles["table_cell"]),
                Paragraph(_display(ROLE_LABELS.get(person.get("role"))), styles["table_cell"]),
            ])
        crew_content = _standard_table(crew_rows, [180 * mm, 87 * mm])
    else:
        crew_content = Paragraph("Keine Besatzung", styles["empty"])
    return [
        CondPageBreak(42 * mm), header, meta, Spacer(1, 2 * mm), crew_content, Spacer(1, 5 * mm)
    ]


def _vehicles_section(operation, vehicles, styles):
    story = _section_title("Fahrzeugübersicht", operation, styles)
    story.extend([_vehicle_summary(vehicles, styles), Spacer(1, 5 * mm)])
    if not vehicles.get("items"):
        story.append(Paragraph("Keine Fahrzeuge vorhanden.", styles["empty"]))
        return story
    for vehicle in vehicles["items"]:
        story.extend(_vehicle_block(vehicle, styles))
    return story


def generate_operation_pdf(operation, sections=None, helpers=None, vehicles=None):
    """Generate a PDF for one or more export sections and return its bytes."""
    sections = list(sections or [SECTION_PATIENTS])
    unknown = set(sections) - set(SECTION_ORDER)
    if not sections or unknown:
        raise ValueError("Ungültige Exportbereiche.")

    styles = _styles()
    buffer = BytesIO()
    export_ts = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    first_orientation = SECTION_ORIENTATION[sections[0]]
    doc = _build_doc(
        buffer, first_orientation, operation.get("name", "Unbekannte Lage"), export_ts
    )

    story = []
    for index, section in enumerate(sections):
        orientation = SECTION_ORIENTATION[section]
        if index:
            story.extend([NextPageTemplate(orientation), PageBreak()])
        if section == SECTION_PATIENTS:
            story.extend(_patient_section(operation, styles))
        elif section == SECTION_HELPERS_SUMMARY:
            story.extend(_helpers_summary_section(operation, helpers or {}, styles))
        elif section == SECTION_HELPERS_DETAIL:
            story.extend(_helpers_detail_section(operation, helpers or {}, styles))
        elif section == SECTION_VEHICLES:
            story.extend(_vehicles_section(operation, vehicles or {}, styles))

    doc.build(story)
    return buffer.getvalue()
