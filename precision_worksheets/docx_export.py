"""Render ProbeSheet objects to a printable, editable Word document."""

from __future__ import annotations

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm
from reportlab.lib.units import cm as POINTS_PER_CM

from .docx_helpers import set_cell_margins, set_cell_text, set_column_widths, set_run_font
from .generator import ProbeSheet
from .layout import fit_grid_font_size

ROW_NUM_COL_CM = 0.8

# A4 portrait, set explicitly rather than relying on Word's default
# template (which isn't guaranteed to be A4).
PAGE_WIDTH_CM = 21.0
PAGE_HEIGHT_CM = 29.7

# Rough space the header (title/name/word list) and footer (scoring line)
# take up, used to work out how much vertical room is left for the grid
# itself - padded well over the true value so an estimation error never
# quietly pushes a sheet onto a near-blank extra page. Word's built-in
# "Heading 1" style carries its own template spacing that runs taller than
# its font size alone would suggest, so this needs more headroom than the
# equivalent estimate in pdf_export.py.
_HEADER_HEIGHT_WITH_WORDLIST_PT = 130
_HEADER_HEIGHT_WITHOUT_WORDLIST_PT = 105
_FOOTER_HEIGHT_PT = 50
_GRID_LEADING_FACTOR = 1.15
_MIN_ROW_PADDING_PT = 10


def export_docx(
    sheets: list[ProbeSheet],
    output_path: str,
    include_word_list: bool = True,
    grid_font_size: int = 20,
) -> None:
    """Write `sheets` to `output_path` as a single multi-page .docx file.

    `grid_font_size` is a ceiling, not a fixed size: a word only shrinks
    below it if it wouldn't otherwise fit on one line in its box. The boxes
    themselves are padded to fill the space left on the page after the
    header/footer, so the grid uses as much of the sheet as it can without
    needing the text itself to be huge.
    """
    if not sheets:
        raise ValueError("No sheets to export")

    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Cm(PAGE_WIDTH_CM)
    section.page_height = Cm(PAGE_HEIGHT_CM)
    section.left_margin = Cm(1.0)
    section.right_margin = Cm(1.0)
    section.top_margin = Cm(1.0)
    section.bottom_margin = Cm(1.0)
    usable_width_emu = section.page_width - section.left_margin - section.right_margin
    usable_width_cm = usable_width_emu / Cm(1)

    for sheet in sheets:
        title = doc.add_heading("Precision Teaching Probe Sheet", level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title.runs:
            set_run_font(run)

        meta = doc.add_paragraph()
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta_run = meta.add_run(
            f"Name: {sheet.child_name}     Date: {sheet.date_str}     "
            f"Sheet {sheet.sheet_number} of {sheet.total_sheets}"
        )
        meta_run.bold = True
        set_run_font(meta_run)

        if include_word_list:
            wp = doc.add_paragraph()
            wp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = wp.add_run("Target words: " + ", ".join(sheet.words))
            run.italic = True
            set_run_font(run)

        table = doc.add_table(rows=sheet.rows, cols=sheet.cols + 1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = "Table Grid"
        table.autofit = False

        col_width_cm = (usable_width_cm - ROW_NUM_COL_CM) / sheet.cols
        set_column_widths(table, [ROW_NUM_COL_CM] + [col_width_cm] * sheet.cols)

        # A word only shrinks below grid_font_size if it wouldn't otherwise
        # fit on one line in its box.
        fitted_font_size = fit_grid_font_size(
            sheet.words, grid_font_size, col_width_cm * POINTS_PER_CM
        )

        # Pad each row so the grid stretches to fill the space left on the
        # page below the header/footer, rather than leaving it mostly blank.
        header_height = (
            _HEADER_HEIGHT_WITH_WORDLIST_PT if include_word_list else _HEADER_HEIGHT_WITHOUT_WORDLIST_PT
        )
        page_height_pt = PAGE_HEIGHT_CM * POINTS_PER_CM
        margins_pt = (section.top_margin + section.bottom_margin) / Cm(1) * POINTS_PER_CM
        available_grid_height = page_height_pt - margins_pt - header_height - _FOOTER_HEIGHT_PT
        target_row_height = available_grid_height / sheet.rows
        text_block_height = fitted_font_size * _GRID_LEADING_FACTOR
        vertical_padding = max(_MIN_ROW_PADDING_PT, (target_row_height - text_block_height) / 2)
        set_cell_margins(table, top_pt=vertical_padding, bottom_pt=vertical_padding, left_pt=6, right_pt=6)

        for r, row_words in enumerate(sheet.grid):
            cells = table.rows[r].cells
            set_cell_text(cells[0], str(r + 1), size_pt=9, bold=False)
            for c, word in enumerate(row_words, start=1):
                set_cell_text(cells[c], word, size_pt=fitted_font_size, bold=True)

        footer = doc.add_paragraph()
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_run = footer.add_run(
            "Time (seconds): _______     Correct: _______     "
            "Errors: _______     Correct per minute: _______"
        )
        set_run_font(footer_run)

        if sheet.sheet_number != sheet.total_sheets:
            doc.add_page_break()

    doc.save(output_path)
