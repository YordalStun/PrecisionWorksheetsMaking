"""A printable, scannable "known words" checklist for the initial
assessment, plus the shared layout math that both the PDF generator and
the OMR reader (omr.py) use so a checkbox drawn on the page and the
checkbox the scanner looks for are always the exact same point.

Each page has a checkbox next to every word (tick = already known) and
four small black squares near the corners. The squares aren't
decoration - omr.py finds them in the scanned image and uses their
positions to work out exactly how the page was scanned (any slight
rotation, scale, or offset), so it can land on every checkbox precisely
without needing OCR or any kind of image-understanding model.
"""

from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .data.word_lists import TIERS_BY_KEY

PAGE_WIDTH, PAGE_HEIGHT = A4

MARGIN = 40.0
COLUMNS = 2
ROWS_PER_COLUMN = 30
WORDS_PER_PAGE = COLUMNS * ROWS_PER_COLUMN

HEADER_HEIGHT = 160.0
FOOTER_HEIGHT = 30.0

MARKER_SIZE = 16.0
MARKER_INSET = 14.0

CHECKBOX_SIZE = 13.0


@dataclass(frozen=True)
class ChecklistPage:
    tier_key: str
    page_index: int  # 1-based
    total_pages: int
    words: tuple[str, ...]  # the words on this page, in on-page order


def paginate(tier_key: str) -> list[ChecklistPage]:
    """Splits a tier's word list into print-ready pages."""
    words = TIERS_BY_KEY[tier_key].words
    chunks = [words[i : i + WORDS_PER_PAGE] for i in range(0, len(words), WORDS_PER_PAGE)]
    total = len(chunks)
    return [
        ChecklistPage(tier_key=tier_key, page_index=i + 1, total_pages=total, words=tuple(chunk))
        for i, chunk in enumerate(chunks)
    ]


def marker_positions() -> dict[str, tuple[float, float]]:
    """The 4 corner marker CENTRES in PDF points (origin bottom-left, same
    as reportlab), keyed by corner. Fixed regardless of page content."""
    m = MARKER_INSET + MARKER_SIZE / 2
    return {
        "tl": (m, PAGE_HEIGHT - m),
        "tr": (PAGE_WIDTH - m, PAGE_HEIGHT - m),
        "bl": (m, m),
        "br": (PAGE_WIDTH - m, m),
    }


def checkbox_centres(num_words: int) -> list[tuple[float, float]]:
    """Checkbox centres in PDF points for a page with `num_words` words,
    filled column-major (same reading order as the on-screen checklist)."""
    col_width = (PAGE_WIDTH - 2 * MARGIN) / COLUMNS
    row_height = (PAGE_HEIGHT - MARGIN - HEADER_HEIGHT - FOOTER_HEIGHT) / ROWS_PER_COLUMN
    top_y = PAGE_HEIGHT - HEADER_HEIGHT

    positions = []
    for i in range(num_words):
        col, row = divmod(i, ROWS_PER_COLUMN)
        x = MARGIN + col * col_width + CHECKBOX_SIZE
        y = top_y - row * row_height - row_height / 2
        positions.append((x, y))
    return positions


def export_checklist_pdf(tier_key: str, path: str, child_name: str = "") -> None:
    """Writes the full multi-page checklist PDF for a tier to `path`."""
    pages = paginate(tier_key)
    tier = TIERS_BY_KEY[tier_key]

    c = canvas.Canvas(path, pagesize=A4)
    for page in pages:
        _draw_page(c, page, tier.label, child_name)
        c.showPage()
    c.save()


def _draw_page(c: canvas.Canvas, page: ChecklistPage, tier_label: str, child_name: str) -> None:
    for x, y in marker_positions().values():
        c.setFillColorRGB(0, 0, 0)
        c.rect(x - MARKER_SIZE / 2, y - MARKER_SIZE / 2, MARKER_SIZE, MARKER_SIZE, fill=1, stroke=0)

    # Header text is kept to short lines that stay well clear of the corner
    # marker search zones (the long combined title used to run far enough
    # right to land inside the top-right marker's own search box).
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGIN + 55, PAGE_HEIGHT - 58, "Known Words Checklist")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN + 55, PAGE_HEIGHT - 76, tier_label)

    c.setFont("Helvetica", 10)
    c.drawString(MARGIN + 55, PAGE_HEIGHT - 92, f"Page {page.page_index} of {page.total_pages}")
    c.drawString(
        MARGIN + 55, PAGE_HEIGHT - 108,
        f"Child: {child_name}" if child_name else "Child: " + "_" * 28,
    )
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(
        MARGIN + 55, PAGE_HEIGHT - 126,
        "Tick the box next to every word the",
    )
    c.drawString(
        MARGIN + 55, PAGE_HEIGHT - 138,
        "child already knows confidently.",
    )

    col_width = (PAGE_WIDTH - 2 * MARGIN) / COLUMNS
    centres = checkbox_centres(len(page.words))
    c.setFont("Helvetica", 12)
    for (x, y), word in zip(centres, page.words):
        c.setStrokeColorRGB(0.55, 0.55, 0.55)
        c.setLineWidth(1)
        c.rect(x - CHECKBOX_SIZE / 2, y - CHECKBOX_SIZE / 2, CHECKBOX_SIZE, CHECKBOX_SIZE, fill=0, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(x + CHECKBOX_SIZE, y - 4, word)

    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawCentredString(
        PAGE_WIDTH / 2, FOOTER_HEIGHT / 2,
        "Scan flat and square, without rotating - Precision Worksheet Maker reads this sheet automatically.",
    )
