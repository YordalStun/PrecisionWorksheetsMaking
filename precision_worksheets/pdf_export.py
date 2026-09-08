"""Render ProbeSheet objects to a printable PDF using reportlab."""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
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

PAGE_WIDTH, PAGE_HEIGHT = A4
# Trimmed down from a more cautious default so the grid boxes get as much
# of the page as possible.
MARGIN = 10 * mm

# Rough space the header (title/name/word list) and footer (scoring line)
# take up, used to work out how much vertical room is left for the grid
# itself - padded a little over the true value so an estimation error
# never quietly pushes a sheet onto an extra page.
_HEADER_HEIGHT_WITH_WORDLIST = 85
_HEADER_HEIGHT_WITHOUT_WORDLIST = 60
_FOOTER_HEIGHT = 32
_GRID_LEADING_FACTOR = 1.15
_MIN_ROW_PADDING = 10

# Progress tracker page, appended once at the end of the sheet set.
TRACKER_TRIES = 10


def export_pdf(
    sheets: list[ProbeSheet],
    output_path: str,
    include_word_list: bool = True,
    grid_font_size: int = 20,
) -> None:
    """Write `sheets` to `output_path` as a single multi-page PDF.

    `grid_font_size` is a ceiling, not a fixed size: a word only shrinks
    below it if it wouldn't otherwise fit on one line in its box. The boxes
    themselves are padded to fill the space left on the page after the
    header/footer, so the grid uses as much of the sheet as it can without
    needing the text itself to be huge.
    """
    if not sheets:
        raise ValueError("No sheets to export")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
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
    row_num_style = ParagraphStyle(
        "PTRowNum",
        parent=styles["Normal"],
        fontName=comic_regular,
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
    )
    tracker_title_style = ParagraphStyle(
        "PTTrackerTitle",
        parent=styles["Title"],
        fontName=comic_bold,
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    tracker_intro_style = ParagraphStyle(
        "PTTrackerIntro",
        parent=styles["Normal"],
        fontName=comic_regular,
        fontSize=10.5,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
        spaceAfter=14,
    )
    tracker_header_style = ParagraphStyle(
        "PTTrackerHeader",
        parent=styles["Normal"],
        fontName=comic_bold,
        fontSize=10.5,
        alignment=TA_CENTER,
    )
    tracker_cell_style = ParagraphStyle(
        "PTTrackerCell",
        parent=styles["Normal"],
        fontName=comic_regular,
        fontSize=10.5,
        alignment=TA_CENTER,
    )

    usable_width = PAGE_WIDTH - 2 * MARGIN
    row_num_width = 8 * mm

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

        grid_col_width = (usable_width - row_num_width) / sheet.cols

        # Words are drawn as big as they can be while still fitting on one
        # line in their box, up to grid_font_size - grows short words up,
        # shrinks long words down, never lets text spill over the lines.
        fitted_font_size = fit_grid_font_size(sheet.words, grid_font_size, grid_col_width)
        # Plain strings in a Table cell don't reliably grow the row height to
        # match a large FONTSIZE, so the word itself is wrapped in a
        # Paragraph - Table sizes rows from a Paragraph's own measured height.
        grid_word_style = ParagraphStyle(
            "PTGridWord",
            parent=styles["Normal"],
            fontName=comic_bold,
            fontSize=fitted_font_size,
            leading=fitted_font_size * 1.15,
            alignment=TA_CENTER,
        )
        data = [
            [Paragraph(str(i), row_num_style)] + [Paragraph(w, grid_word_style) for w in row]
            for i, row in enumerate(sheet.grid, start=1)
        ]
        col_widths = [row_num_width] + [grid_col_width] * sheet.cols

        # Pad each row so the grid stretches to fill the space left on the
        # page below the header/footer, rather than leaving it mostly blank.
        header_height = (
            _HEADER_HEIGHT_WITH_WORDLIST if include_word_list else _HEADER_HEIGHT_WITHOUT_WORDLIST
        )
        available_grid_height = (PAGE_HEIGHT - 2 * MARGIN) - header_height - _FOOTER_HEIGHT
        target_row_height = available_grid_height / sheet.rows
        text_block_height = fitted_font_size * _GRID_LEADING_FACTOR
        vertical_padding = max(_MIN_ROW_PADDING, (target_row_height - text_block_height) / 2)

        table = Table(data, colWidths=col_widths, repeatRows=0)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.75, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eeeeee")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), vertical_padding),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), vertical_padding),
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

        story.append(PageBreak())

    # A one-off progress tracker page at the end, so the same 10-column
    # rows can log tries across multiple days without any date being
    # guessed or pre-filled - the child/family writes each one in by hand.
    story.append(Paragraph("Progress Tracker", tracker_title_style))
    story.append(
        Paragraph(
            "Log up to 10 tries at this probe sheet across as many days as you like.",
            tracker_intro_style,
        )
    )

    tracker_headers = ["Try", "Date", "Time (sec)", "Correct", "Errors", "Correct/min"]
    tracker_data = [[Paragraph(h, tracker_header_style) for h in tracker_headers]]
    for i in range(1, TRACKER_TRIES + 1):
        tracker_data.append(
            [Paragraph(str(i), tracker_cell_style)] + [Paragraph("", tracker_cell_style) for _ in range(5)]
        )

    tracker_col_width = usable_width / len(tracker_headers)
    tracker_table = Table(
        tracker_data,
        colWidths=[tracker_col_width] * len(tracker_headers),
        rowHeights=[24] + [26] * TRACKER_TRIES,
        repeatRows=1,
    )
    tracker_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.75, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(tracker_table)

    doc.build(story)
