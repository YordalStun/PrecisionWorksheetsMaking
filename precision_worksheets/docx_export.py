"""Render ProbeSheet objects to a printable, editable Word document."""

from __future__ import annotations

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt

from .generator import ProbeSheet

ROW_NUM_COL_CM = 1.0


def export_docx(
    sheets: list[ProbeSheet],
    output_path: str,
    include_word_list: bool = True,
    grid_font_size: int = 18,
) -> None:
    """Write `sheets` to `output_path` as a single multi-page .docx file."""
    if not sheets:
        raise ValueError("No sheets to export")

    doc = Document()
    section = doc.sections[0]
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    usable_width_emu = section.page_width - section.left_margin - section.right_margin
    usable_width_cm = usable_width_emu / Cm(1)

    for sheet in sheets:
        title = doc.add_heading("Precision Teaching Probe Sheet", level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        meta = doc.add_paragraph()
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta.add_run(
            f"Name: {sheet.child_name}     Date: {sheet.date_str}     "
            f"Sheet {sheet.sheet_number} of {sheet.total_sheets}"
        ).bold = True

        if include_word_list:
            wp = doc.add_paragraph()
            wp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = wp.add_run("Target words: " + ", ".join(sheet.words))
            run.italic = True

        table = doc.add_table(rows=sheet.rows, cols=sheet.cols + 1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = "Table Grid"
        table.autofit = False

        col_width_cm = (usable_width_cm - ROW_NUM_COL_CM) / sheet.cols
        _set_column_widths(table, [ROW_NUM_COL_CM] + [col_width_cm] * sheet.cols)

        for r, row_words in enumerate(sheet.grid):
            cells = table.rows[r].cells
            _set_cell_text(cells[0], str(r + 1), size_pt=9, bold=False)
            for c, word in enumerate(row_words, start=1):
                _set_cell_text(cells[c], word, size_pt=grid_font_size, bold=True)

        footer = doc.add_paragraph()
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.add_run(
            "Time (seconds): _______     Correct: _______     "
            "Errors: _______     Correct per minute: _______"
        )

        if sheet.sheet_number != sheet.total_sheets:
            doc.add_page_break()

    doc.save(output_path)


def _set_cell_text(cell, text: str, size_pt: int, bold: bool) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(text)
    run.font.size = Pt(size_pt)
    run.font.bold = bold


def _set_column_widths(table, widths_cm: list[float]) -> None:
    """python-docx needs the width set on every cell, not just the column,
    for Word to respect it reliably."""
    table.autofit = False
    for row in table.rows:
        for cell, width in zip(row.cells, widths_cm):
            cell.width = Cm(width)
    # Also disable the table's auto-layout so fixed widths stick.
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
