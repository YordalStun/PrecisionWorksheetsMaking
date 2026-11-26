"""Printable progress report for one child - evidence of improvement (e.g. for Ofsted)."""

from __future__ import annotations

import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import db

KIND_LABELS = {"initial": "Initial assessment", "retest": "Re-assessment",
               "initial (rebuilt)": "Initial assessment (rebuilt from records)"}


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


def export_progress_report(conn, child_id: int, path: str) -> None:
    data = db.progress_summary(conn, child_id)
    child = data["child"]
    styles = getSampleStyleSheet()
    h1, h2, body = styles["Title"], styles["Heading2"], styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=9, leading=11)

    def table(rows, widths, header_bg="#dbeafe"):
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ]))
        return t

    story = [
        Paragraph(f"Progress report: {child['name']}", h1),
        Paragraph(
            f"Year group: {child['year_group'] or '-'} &nbsp;&nbsp; Word list: {data['tier_label']} &nbsp;&nbsp; "
            f"Report date: {datetime.date.today().strftime('%d/%m/%Y')}", body),
        Spacer(1, 6 * mm),
        Paragraph("Summary", h2),
        table([
            [Paragraph(f"<b>{h}</b>", small) for h in
             ("Known at first assessment", "Known now", "Learned through practice", "Words practised", "Practice sessions")],
            [f"{data['known_at_start']} / {data['tier_total']}", f"{len(data['known_now'])} / {data['tier_total']}",
             str(len(data["learned"])), str(len(data["practised"])), str(data["sessions"])],
        ], [36 * mm] * 5),
        Spacer(1, 6 * mm),
        Paragraph("Known-words assessments", h2),
    ]

    rows = [["Date", "Assessment", "Known", "New since previous"]]
    for a in data["assessments"]:
        gained = ", ".join(a["gained"]) if a["gained"] else ("-" if a["kind"] != "retest" else "none")
        rows.append([a["date"], Paragraph(kind_label(a["kind"]), small), str(len(a["known"])), Paragraph(gained, small)])
    story.append(table(rows, [24 * mm, 46 * mm, 18 * mm, 92 * mm]))
    for a in data["assessments"]:
        story += [Spacer(1, 3 * mm),
                  Paragraph(f"<b>{a['date']} - {kind_label(a['kind'])}</b>: words known ({len(a['known'])})", small),
                  Paragraph(", ".join(a["known"]) or "none", small)]

    story += [Spacer(1, 6 * mm), Paragraph("Words practised", h2)]
    rows = [["Word", "First practised", "Times practised", "Times correct", "Now"]]
    for r in data["practised"]:
        rows.append([r["word"], r["first"], str(r["seen"]), str(r["correct"]),
                     "Known" if r["status"] == db.STATUS_KNOWN else "Still learning"])
    if len(rows) == 1:
        rows.append(["No practice sessions recorded yet", "", "", "", ""])
    story.append(table(rows, [40 * mm, 32 * mm, 32 * mm, 32 * mm, 44 * mm]))

    story += [Spacer(1, 6 * mm), Paragraph(f"Words learned through practice ({len(data['learned'])})", h2),
              Paragraph(", ".join(data["learned"]) or "None yet.", body),
              Spacer(1, 4 * mm), Paragraph(f"All words known now ({len(data['known_now'])})", h2),
              Paragraph(", ".join(data["known_now"]) or "None yet.", body)]

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title=f"Progress report - {child['name']}")
    doc.build(story)
