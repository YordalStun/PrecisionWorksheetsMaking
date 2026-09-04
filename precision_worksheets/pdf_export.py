"""Render ProbeSheet objects to a printable PDF using reportlab."""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .fonts import get_comic_font_names
from .generator import ProbeSheet
from .layout import fit_grid_font_size

# Landscape gives noticeably wider boxes than portrait for a grid that's
# wider than it is tall (the default is 5 columns x 4 rows), which is the
# main lever for making the words-in-boxes bigger without shrinking text.
PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
MARGIN = 14 * mm


def export_pdf(
    sheets: list[ProbeSheet],
    output_path: str,
    include_word_list: bool = True,
    grid_font_size: int = 18,
) -> None:
    """Write `sheets` to `output_path` as a single multi-page PDF."""
    if not sheets:
        raise ValueError("No sheets to export")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        title="Precision Teaching Probe Sheet",
    )

    comic_regular, comic_bold = get_comic_font_names()

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PTTitle",
        parent=styles["Title"],
        fontName=comic_bold,
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "PTMeta",
        parent=styles["Normal"],
        fontName=comic_regular,
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    word_style = ParagraphStyle(
        "PTWords",
        parent=styles["Normal"],
        fontName=comic_regular,
        fontSize=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
        spaceAfter=8,
    )
    footer_style = ParagraphStyle(
        "PTFooter",
        parent=styles["Normal"],
        fontName=comic_regular,
        fontSize=11,
        alignment=TA_CENTER,
        spaceBefore=10,
    )

    usable_width = PAGE_WIDTH - 2 * MARGIN
    row_num_width = 10 * mm

    story = []
    for sheet in sheets:
        story.append(Paragraph("Precision Teaching Probe Sheet", title_style))
        story.append(
            Paragraph(
                f"Name: {sheet.child_name} &nbsp;&nbsp;&nbsp;&nbsp; "
                f"Date: {sheet.date_str} &nbsp;&nbsp;&nbsp;&nbsp; "
                f"Sheet {sheet.sheet_number} of {sheet.total_sheets}",
                meta_style,
            )
        )
        if include_word_list:
            story.append(Paragraph("Target words: " + ", ".join(sheet.words), word_style))
        story.append(Spacer(1, 6))

        data = [[str(i)] + row for i, row in enumerate(sheet.grid, start=1)]
        grid_col_width = (usable_width - row_num_width) / sheet.cols
        col_widths = [row_num_width] + [grid_col_width] * sheet.cols

        # Shrink the font below the requested size only if a word would
        # otherwise be too wide for its box - never grow past what was asked.
        fitted_font_size = fit_grid_font_size(sheet.words, grid_font_size, grid_col_width)

        table = Table(data, colWidths=col_widths, repeatRows=0)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.75, colors.grey),
                    ("FONTNAME", (1, 0), (-1, -1), comic_bold),
                    ("FONTSIZE", (1, 0), (-1, -1), fitted_font_size),
                    ("FONTNAME", (0, 0), (0, -1), comic_regular),
                    ("FONTSIZE", (0, 0), (0, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eeeeee")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        story.append(table)

        story.append(
            Paragraph(
                "Time (seconds): _______ &nbsp;&nbsp;&nbsp; "
                "Correct: _______ &nbsp;&nbsp;&nbsp; "
                "Errors: _______ &nbsp;&nbsp;&nbsp; "
                "Correct per minute: _______",
                footer_style,
            )
        )

        if sheet.sheet_number != sheet.total_sheets:
            story.append(PageBreak())

    doc.build(story)
