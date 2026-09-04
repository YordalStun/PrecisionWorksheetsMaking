"""Render ProbeSheet objects to a printable, editable Word document."""

from __future__ import annotations

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Cm, Pt
from reportlab.lib.units import cm as POINTS_PER_CM

from .generator import ProbeSheet
from .layout import fit_grid_font_size

ROW_NUM_COL_CM = 0.8

# A4 portrait, set explicitly rather than relying on Word's default
# template (which isn't guaranteed to be A4).
PAGE_WIDTH_CM = 21.0
PAGE_HEIGHT_CM = 29.7

# Comic Sans MS ships with every edition of Windows, so referencing it by
# name (rather than embedding a font file) is reliable for a Windows app -
# Word just uses whatever copy is already installed on the machine.
COMIC_FONT_NAME = "Comic Sans MS"


def export_docx(
    sheets: list[ProbeSheet],
    output_path: str,
    include_word_list: bool = True,
    grid_font_size: int = 60,
) -> None:
    """Write `sheets` to `output_path` as a single multi-page .docx file.

    `grid_font_size` is a ceiling, not a fixed size: each sheet's words are
    drawn as large as they can be while still fitting on one line in their
    box, up to this cap.
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
            _set_run_font(run)

        meta = doc.add_paragraph()
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta_run = meta.add_run(
            f"Name: {sheet.child_name}     Date: {sheet.date_str}     "
            f"Sheet {sheet.sheet_number} of {sheet.total_sheets}"
        )
        meta_run.bold = True
        _set_run_font(meta_run)

        if include_word_list:
            wp = doc.add_paragraph()
            wp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = wp.add_run("Target words: " + ", ".join(sheet.words))
            run.italic = True
            _set_run_font(run)

        table = doc.add_table(rows=sheet.rows, cols=sheet.cols + 1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = "Table Grid"
        table.autofit = False

        col_width_cm = (usable_width_cm - ROW_NUM_COL_CM) / sheet.cols
        _set_column_widths(table, [ROW_NUM_COL_CM] + [col_width_cm] * sheet.cols)
        _set_cell_margins(table, top_pt=14, bottom_pt=14, left_pt=6, right_pt=6)

        # Words are drawn as big as they can be while still fitting on one
        # line in their box, up to grid_font_size - grows short words up,
        # shrinks long words down, never lets text spill over the lines.
        fitted_font_size = fit_grid_font_size(
            sheet.words, grid_font_size, col_width_cm * POINTS_PER_CM
        )

        for r, row_words in enumerate(sheet.grid):
            cells = table.rows[r].cells
            _set_cell_text(cells[0], str(r + 1), size_pt=9, bold=False)
            for c, word in enumerate(row_words, start=1):
                _set_cell_text(cells[c], word, size_pt=fitted_font_size, bold=True)

        footer = doc.add_paragraph()
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_run = footer.add_run(
            "Time (seconds): _______     Correct: _______     "
            "Errors: _______     Correct per minute: _______"
        )
        _set_run_font(footer_run)

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
    _set_run_font(run)


def _set_run_font(run, name: str = COMIC_FONT_NAME) -> None:
    run.font.name = name
    # Word can pick a different font for the "complex script" slot even
    # when w:ascii/w:hAnsi are set, so pin that explicitly too.
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:cs"), name)


def _set_cell_margins(table, top_pt: float, bottom_pt: float, left_pt: float, right_pt: float) -> None:
    """python-docx has no direct API for cell padding, so set it via the
    table-wide tblCellMar - twentieths of a point (dxa) per the OOXML spec.

    tblPr's children must stay in schema order (tblLayout, then tblCellMar,
    then tblLook, ...), so this is inserted before tblLook rather than just
    appended - a plain append would land after tblLook, which python-docx's
    add_table() already added.
    """
    tbl_pr = table._tbl.tblPr
    cell_mar = OxmlElement("w:tblCellMar")
    for tag, value_pt in (("top", top_pt), ("bottom", bottom_pt), ("left", left_pt), ("right", right_pt)):
        node = OxmlElement(f"w:{tag}")
        node.set(qn("w:w"), str(int(value_pt * 20)))
        node.set(qn("w:type"), "dxa")
        cell_mar.append(node)
    tbl_pr.insert_element_before(
        cell_mar, "w:tblLook", "w:tblCaption", "w:tblDescription", "w:tblPrChange"
    )


def _set_column_widths(table, widths_cm: list[float]) -> None:
    """python-docx needs the width set on every cell, not just the column,
    for Word to respect it reliably. Setting autofit=False already adds a
    correctly-ordered `w:tblLayout type="fixed"` (see CT_TblPr.autofit), so
    there's no need to add a second one by hand."""
    table.autofit = False
    for row in table.rows:
        for cell, width in zip(row.cells, widths_cm):
            cell.width = Cm(width)
