"""Auto-shrink the grid word font so text never overflows its box.

A box's width is fixed by the page size and the number of columns, so if a
word is too wide to fit at the requested font size, the font has to give
way rather than the text spilling across the grid lines. Both the PDF and
Word exporters measure against the same font (whichever real font
fonts.get_comic_font_names() found - or its Helvetica fallback) so the two
file formats end up sized consistently.
"""

from __future__ import annotations

from reportlab.pdfbase import pdfmetrics

from .fonts import get_comic_font_names

MIN_GRID_FONT_SIZE = 10

# Leave a margin either side of the measured text rather than letting it
# touch the grid line exactly.
_WIDTH_SAFETY_FACTOR = 0.85


def fit_grid_font_size(words: list[str], requested_size: int, cell_width_pt: float) -> int:
    """Return the largest font size, at most `requested_size`, at which every
    word in `words` still fits within a box `cell_width_pt` points wide."""
    if not words:
        return requested_size

    _, bold_font_name = get_comic_font_names()
    max_text_width = cell_width_pt * _WIDTH_SAFETY_FACTOR

    size = requested_size
    while size > MIN_GRID_FONT_SIZE:
        widest = max(pdfmetrics.stringWidth(w, bold_font_name, size) for w in words)
        if widest <= max_text_width:
            return size
        size -= 1
    return MIN_GRID_FONT_SIZE
