"""Large-print word sheets: each of the child's words shown alone, as big as
possible, one per landscape page - nothing else on the page, for a quick
flashcard-style look at a single word (e.g. holding it up, or for a child
who needs bigger print).

Each word is rendered once as a Pillow image, centred on its own ink via
PIL's "mm" (middle/middle) text anchor, and that same image is then
embedded unchanged into both the PDF and the Word doc - the same approach
the board/trail games use elsewhere in this app, and for the same reason:
native PDF/Word text layout centres a font's line box, not the glyph ink,
which visibly off-centres a single big word; a pre-rendered image sidesteps
that entirely and keeps both formats identical.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .fonts import get_board_font_paths
from .games._drawing import FRAME_PADDING, image_to_png_bytes

_IMG_WIDTH = 2339
_IMG_HEIGHT = 1654
_MARGIN = 90
_MAX_FONT_SIZE = 900
_MIN_FONT_SIZE = 40

_DOCX_PAGE_SIZE_CM = (29.7, 21.0)
_DOCX_MARGIN_CM = 1.0


@dataclass
class LargePrintPage:
    word: str


def build_large_print_pages(words: list[str]) -> list[LargePrintPage]:
    clean_words = [w.strip() for w in words if w.strip()]
    if not clean_words:
        raise ValueError("At least one word is required")
    return [LargePrintPage(word=word) for word in clean_words]


def _fit_font_by_width_and_height(
    draw: ImageDraw.ImageDraw, text: str, font_path: str, max_size: int, max_width: float, max_height: float, min_size: int
) -> ImageFont.FreeTypeFont:
    size = max_size
    while size > min_size:
        font = ImageFont.truetype(font_path, size)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        if right - left <= max_width and bottom - top <= max_height:
            return font
        size -= 4
    return ImageFont.truetype(font_path, min_size)


def render_large_print_image(word: str) -> Image.Image:
    img = Image.new("RGB", (_IMG_WIDTH, _IMG_HEIGHT), "white")
    draw = ImageDraw.Draw(img)
    _, bold_path = get_board_font_paths()
    max_width = _IMG_WIDTH - 2 * _MARGIN
    max_height = _IMG_HEIGHT - 2 * _MARGIN
    font = _fit_font_by_width_and_height(draw, word, bold_path, _MAX_FONT_SIZE, max_width, max_height, _MIN_FONT_SIZE)

    # Centre on the word's actual ink, not PIL's "mm" anchor - that centres
    # the font's ascender-to-descender box, which for a word like "jump"
    # (whose lowercase letters don't reach the font's full ascent) still
    # visibly off-centres the glyphs. textbbox at the default ("la") anchor
    # gives the true ink box relative to the draw point, so we can work out
    # exactly where to draw from to land that box on the image centre.
    left, top, right, bottom = draw.textbbox((0, 0), word, font=font)
    x = _IMG_WIDTH / 2 - (left + right) / 2
    y = _IMG_HEIGHT / 2 - (top + bottom) / 2
    draw.text((x, y), word, font=font, fill=(0, 0, 0))
    return img


def export_large_print_pdf(pages: list[LargePrintPage], output_path: str) -> None:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage, PageBreak, SimpleDocTemplate

    if not pages:
        raise ValueError("No pages to export")

    page_width, page_height = landscape(A4)
    margin = 10 * mm
    doc = SimpleDocTemplate(
        output_path, pagesize=landscape(A4),
        topMargin=margin, bottomMargin=margin, leftMargin=margin, rightMargin=margin,
        title="Large Print Words",
    )
    usable_width = page_width - 2 * margin - FRAME_PADDING
    usable_height = page_height - 2 * margin - FRAME_PADDING

    story = []
    for i, page in enumerate(pages):
        img = render_large_print_image(page.word)
        png_bytes = image_to_png_bytes(img)
        aspect = img.height / img.width
        draw_width = usable_width
        draw_height = draw_width * aspect
        if draw_height > usable_height:
            draw_height = usable_height
            draw_width = draw_height / aspect
        story.append(RLImage(io.BytesIO(png_bytes), width=draw_width, height=draw_height))
        if i != len(pages) - 1:
            story.append(PageBreak())

    doc.build(story)


def export_large_print_docx(pages: list[LargePrintPage], output_path: str) -> None:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.shared import Cm

    if not pages:
        raise ValueError("No pages to export")

    width_cm, height_cm = _DOCX_PAGE_SIZE_CM
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Cm(width_cm)
    section.page_height = Cm(height_cm)
    section.left_margin = Cm(_DOCX_MARGIN_CM)
    section.right_margin = Cm(_DOCX_MARGIN_CM)
    section.top_margin = Cm(_DOCX_MARGIN_CM)
    section.bottom_margin = Cm(_DOCX_MARGIN_CM)
    usable_width_cm = (section.page_width - section.left_margin - section.right_margin) / Cm(1)

    for i, page in enumerate(pages):
        img = render_large_print_image(page.word)
        png_bytes = image_to_png_bytes(img)
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.add_run().add_picture(io.BytesIO(png_bytes), width=Cm(usable_width_cm))
        # A break run in the same paragraph as the image, rather than
        # doc.add_page_break() (which appends a whole extra paragraph and
        # renders as its own blank page before the break takes effect).
        if i != len(pages) - 1:
            paragraph.add_run().add_break(WD_BREAK.PAGE)

    doc.save(output_path)
