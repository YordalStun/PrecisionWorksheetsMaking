"""Pick the biggest grid word font that still fits inside its box.

A box's width is fixed by the page size and the number of columns, so the
text should be exactly as big as it can be while still fitting on one
line - any bigger and a word would have to wrap. This searches downward
from `max_size` for the largest size that still fits, which naturally
covers both directions: it grows short words in a roomy box up towards the
cap, and shrinks long words in a narrow box down below it. Both the PDF and
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


def fit_grid_font_size(words: list[str], max_size: int, cell_width_pt: float) -> int:
    """Return the largest font size, at most `max_size`, at which every word
    in `words` still fits on one line within a box `cell_width_pt` points wide."""
    if not words:
        return max_size

    _, bold_font_name = get_comic_font_names()
    max_text_width = cell_width_pt * _WIDTH_SAFETY_FACTOR

    size = max_size
    while size > MIN_GRID_FONT_SIZE:
        widest = max(pdfmetrics.stringWidth(w, bold_font_name, size) for w in words)
        if widest <= max_text_width:
            return size
        size -= 1
    return MIN_GRID_FONT_SIZE
