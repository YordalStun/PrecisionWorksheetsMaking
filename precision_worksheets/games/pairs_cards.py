"""Word-pairs matching (memory) game: a sheet of big cut-out cards, each
target word appearing on exactly two cards, for a face-down pairs game -
cut the cards apart, shuffle, then take turns flipping two at a time
looking for a match.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm
from reportlab.lib.units import cm as POINTS_PER_CM

from ..docx_helpers import set_cell_margins, set_cell_text, set_column_widths, set_run_font
from ..fonts import get_comic_font_names
from ..generator import generate_word_grid
from ..layout import fit_grid_font_size

CARDS_PER_WORD = 2
CARD_COLS = 2

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 12 * mm
CARD_FONT_CAP = 60

INSTRUCTIONS = (
    "Cut out the cards along the lines. Shuffle them and lay them face "
    "down in rows. Take turns flipping two cards over - say each word out "
    "loud. If they match, keep the pair and go again. If not, turn them "
    "back face down. The player with the most pairs at the end wins!"
)


@dataclass
class PairsCardSheet:
    child_name: str
    date_str: str
    words: list[str]
    cards: list[list[str]]  # rows x CARD_COLS grid, each word appears twice

    @property
    def rows(self) -> int:
        return len(self.cards)


def build_pairs_card_sheet(
    child_name: str, words: list[str], date_str: str, seed: int | None = None
) -> PairsCardSheet:
    """Lay out `words` (each appearing twice) onto a CARD_COLS-wide grid."""
    clean_words = [w.strip() for w in words if w.strip()]
    if not clean_words:
        raise ValueError("At least one word is required")

    rng = random.Random(seed)
    total_cards = len(clean_words) * CARDS_PER_WORD
    rows = -(-total_cards // CARD_COLS)  # ceil division
    cards = generate_word_grid(clean_words, rows, CARD_COLS, rng)
    return PairsCardSheet(child_name=child_name, date_str=date_str, words=clean_words, cards=cards)


def export_pairs_cards_pdf(sheet: PairsCardSheet, output_path: str) -> None:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        title="Word Pairs Matching Game",
    )
    comic_regular, comic_bold = get_comic_font_names()
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "PCTitle", parent=styles["Title"], fontName=comic_bold, fontSize=20,
        alignment=TA_CENTER, spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "PCMeta", parent=styles["Normal"], fontName=comic_regular, fontSize=11,
        alignment=TA_CENTER, spaceAfter=6,
    )
    instructions_style = ParagraphStyle(
        "PCInstructions", parent=styles["Normal"], fontName=comic_regular, fontSize=10,
        alignment=TA_CENTER, textColor=colors.HexColor("#444444"), spaceAfter=10,
    )

    usable_width = PAGE_WIDTH - 2 * MARGIN
    header_flowables = [
        Paragraph("Word Pairs Matching Game", title_style),
        Paragraph(f"For {sheet.child_name} &nbsp;&nbsp;&nbsp; Date: {sheet.date_str}", meta_style),
        Paragraph(INSTRUCTIONS, instructions_style),
        Spacer(1, 4),
    ]
    story = list(header_flowables)
    # Measure the header's actual wrapped height (the instructions line
    # wraps to 2-3 lines depending on the name) rather than guessing it -
    # an underestimate would quietly push the last card row onto its own
    # near-blank second page.
    header_height = sum(f.wrap(usable_width, PAGE_HEIGHT)[1] for f in header_flowables)

    card_width = usable_width / CARD_COLS
    fitted_font_size = fit_grid_font_size(sheet.words, CARD_FONT_CAP, card_width)
    card_style = ParagraphStyle(
        "PCCard", parent=styles["Normal"], fontName=comic_bold,
        fontSize=fitted_font_size, leading=fitted_font_size * 1.15, alignment=TA_CENTER,
    )

    # Paragraph.wrap() doesn't include spaceBefore/spaceAfter or the
    # default frame's own padding, so leave a generous cushion rather than
    # sizing the table to the exact remaining space.
    available_height = (PAGE_HEIGHT - 2 * MARGIN) - header_height - 60
    target_row_height = available_height / sheet.rows
    text_block_height = fitted_font_size * 1.15
    vertical_padding = max(10, (target_row_height - text_block_height) / 2)

    data = [[Paragraph(word, card_style) for word in row] for row in sheet.cards]
    table = Table(data, colWidths=[card_width] * CARD_COLS)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1.25, colors.grey, None, [4, 3]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), vertical_padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), vertical_padding),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    doc.build(story)


def export_pairs_cards_docx(sheet: PairsCardSheet, output_path: str) -> None:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(1.2)
    section.right_margin = Cm(1.2)
    section.top_margin = Cm(1.2)
    section.bottom_margin = Cm(1.2)
    usable_width_cm = (section.page_width - section.left_margin - section.right_margin) / Cm(1)

    title = doc.add_heading("Word Pairs Matching Game", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in title.runs:
        set_run_font(run)

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta.add_run(f"For {sheet.child_name}     Date: {sheet.date_str}")
    meta_run.bold = True
    set_run_font(meta_run)

    instructions = doc.add_paragraph()
    instructions.alignment = WD_ALIGN_PARAGRAPH.CENTER
    instructions_run = instructions.add_run(INSTRUCTIONS)
    instructions_run.italic = True
    set_run_font(instructions_run)

    table = doc.add_table(rows=sheet.rows, cols=CARD_COLS)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    table.autofit = False

    card_width_cm = usable_width_cm / CARD_COLS
    set_column_widths(table, [card_width_cm] * CARD_COLS)

    fitted_font_size = fit_grid_font_size(sheet.words, CARD_FONT_CAP, card_width_cm * POINTS_PER_CM)

    # Generous estimate: Word's built-in Heading 1 style carries more
    # spacing than its font size alone suggests, and the instructions line
    # wraps to 2-3 lines depending on the child's name.
    header_reserve_pt = 200
    page_height_pt = 29.7 * POINTS_PER_CM
    margins_pt = (section.top_margin + section.bottom_margin) / Cm(1) * POINTS_PER_CM
    available_height = page_height_pt - margins_pt - header_reserve_pt
    target_row_height = available_height / sheet.rows
    text_block_height = fitted_font_size * 1.15
    vertical_padding = max(10, (target_row_height - text_block_height) / 2)
    set_cell_margins(table, top_pt=vertical_padding, bottom_pt=vertical_padding, left_pt=6, right_pt=6)

    for r, row_words in enumerate(sheet.cards):
        cells = table.rows[r].cells
        for c, word in enumerate(row_words):
            set_cell_text(cells[c], word, size_pt=fitted_font_size, bold=True)

    doc.save(output_path)
