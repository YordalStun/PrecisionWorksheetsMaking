"""A simple word trail: a winding path of circles from Start to Finish,
each showing one of the target words, in the style of a printable
"roll and read" race track. Roll a die, move that many circles along the
trail, and read the word out loud when you land.

Available in A4 or A3 - A3 keeps the same 27 circles, just bigger, rather
than adding more of them.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from ..fonts import get_board_font_paths
from ..generator import generate_word_grid
from ._drawing import export_full_page_image_docx, export_full_page_image_pdf, fit_font, wrap_text

CIRCLES_PER_ROW = 6
NUM_ROWS = 4
_TOTAL_SLOTS = CIRCLES_PER_ROW + 2  # + a reserved connector slot on each side

# Layout, in "logical" A4-page pixels (drawn at SUPERSAMPLE x this and
# downscaled for anti-aliased circle edges). The A3 variant scales every
# one of these by A3_SCALE rather than changing the trail's shape.
SUPERSAMPLE = 2
BASE_IMG_WIDTH = 1654
BASE_IMG_HEIGHT = 2339
BASE_MARGIN = 60
BASE_CIRCLE_DIAMETER = 150
BASE_ROW_SPACING = 420
BASE_TRAIL_TOP = 260

# A3 has double the area of A4 at the same aspect ratio, so every linear
# dimension - circle size, spacing, font sizes - scales by root 2.
A3_SCALE = math.sqrt(2)

COLOR_OUTLINE = (40, 40, 40)
COLOR_FILL = (255, 255, 255)
COLOR_START_FILL = (200, 235, 200)
COLOR_FINISH_FILL = (255, 221, 130)
COLOR_TEXT = (30, 30, 30)
COLOR_MUTED = (90, 90, 90)
COLOR_PATH = (60, 150, 95)

# How wiggly the connecting trail line is: waves per gap, and amplitude as
# a fraction of that gap's own visible length (not the circle diameter) -
# so a short gap between same-row neighbours still shows a clear wiggle
# rather than a nearly-straight sliver, and a long gap between rows scales
# up to match.
_PATH_WAVES_PER_SEGMENT = 2
_PATH_AMPLITUDE_FACTOR = 0.45

# The circles themselves also bob up and down a little along each row
# (not just the connecting line between them), as a fraction of the
# circle's own radius, so neighbouring circles sit at slightly different
# heights rather than in a rigid straight line.
_ROW_BOB_AMPLITUDE_FACTOR = 0.4
_ROW_BOB_WAVES = 1.5


@dataclass
class WordTrail:
    child_name: str
    words: list[str]
    trail: list[str]  # words in path order, one per circle (Start first, Finish last)


def build_word_trail(child_name: str, words: list[str], seed: int | None = None) -> WordTrail:
    """Lay out `words`, repeated and shuffled, onto every circle of the trail."""
    clean_words = [w.strip() for w in words if w.strip()]
    if not clean_words:
        raise ValueError("At least one word is required")

    rng = random.Random(seed)
    total_circles = NUM_ROWS * CIRCLES_PER_ROW + (NUM_ROWS - 1)
    trail = generate_word_grid(clean_words, rows=1, cols=total_circles, rng=rng)[0]
    return WordTrail(child_name=child_name, words=clean_words, trail=trail)


@dataclass
class _Layout:
    """All the trail's pixel geometry for one page size - identical shape
    to the base A4 layout, just scaled up or down by `k`."""

    k: float

    @property
    def img_width(self) -> float:
        return BASE_IMG_WIDTH * self.k

    @property
    def img_height(self) -> float:
        return BASE_IMG_HEIGHT * self.k

    @property
    def margin(self) -> float:
        return BASE_MARGIN * self.k

    @property
    def circle_diameter(self) -> float:
        return BASE_CIRCLE_DIAMETER * self.k

    @property
    def row_spacing(self) -> float:
        return BASE_ROW_SPACING * self.k

    @property
    def trail_top(self) -> float:
        return BASE_TRAIL_TOP * self.k

    @property
    def slot_spacing(self) -> float:
        return (self.img_width - 2 * self.margin - self.circle_diameter) / (_TOTAL_SLOTS - 1)

    def slot_x(self, slot: int) -> float:
        return self.margin + self.circle_diameter / 2 + slot * self.slot_spacing

    def column_x(self, col: int) -> float:
        """Word column `col` (0..CIRCLES_PER_ROW - 1) sits in slots 1..6."""
        return self.slot_x(col + 1)

    def row_y(self, row: int) -> float:
        return self.trail_top + self.circle_diameter / 2 + row * self.row_spacing

    def column_bob(self, col: int) -> float:
        """Small vertical offset for word column `col`, so consecutive
        circles along a row sit a little higher/lower than their
        neighbours rather than in a rigid straight line."""
        phase = col / (CIRCLES_PER_ROW - 1) * 2 * math.pi * _ROW_BOB_WAVES
        return (self.circle_diameter / 2) * _ROW_BOB_AMPLITUDE_FACTOR * math.sin(phase)


def _layout_for(page_size: str) -> _Layout:
    if page_size not in ("A4", "A3"):
        raise ValueError(f"Unsupported page_size {page_size!r} - use 'A4' or 'A3'")
    return _Layout(k=A3_SCALE if page_size == "A3" else 1.0)


def _draw_wavy_segment(
    draw: ImageDraw.ImageDraw,
    p1: tuple[float, float],
    p2: tuple[float, float],
    radius: float,
    width: float,
) -> None:
    """A gently wavy (snake-like) line between two circles of radius
    `radius` centred at p1 and p2. Only the gap between the circle edges
    is drawn (not the full centre-to-centre span, most of which the
    circles themselves cover) - short gaps between neighbouring circles
    in the same row would otherwise be almost entirely hidden, leaving no
    visible room for a wiggle. The wiggle's amplitude is a fraction of
    that gap's own length, so a short gap still shows a clear wiggle
    rather than a nearly-straight sliver."""
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length <= 2 * radius:
        return
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    gap_x1, gap_y1 = x1 + ux * radius, y1 + uy * radius
    gap_dx, gap_dy = dx - 2 * ux * radius, dy - 2 * uy * radius
    gap_length = length - 2 * radius
    amplitude = gap_length * _PATH_AMPLITUDE_FACTOR
    n = max(10, int(gap_length / 8))
    points = []
    for i in range(n + 1):
        t = i / n
        bx, by = gap_x1 + gap_dx * t, gap_y1 + gap_dy * t
        offset = math.sin(t * math.pi * _PATH_WAVES_PER_SEGMENT) * amplitude
        points.append((bx + px * offset, by + py * offset))
    draw.line(points, fill=COLOR_PATH, width=int(width), joint="curve")


def _row_positions(layout: _Layout, row: int, left_to_right: bool) -> list[tuple[float, float]]:
    """The 6 word-circle centres for one row, in path-visiting order, each
    bobbing up/down a little from the row's base height."""
    cols = range(CIRCLES_PER_ROW) if left_to_right else range(CIRCLES_PER_ROW - 1, -1, -1)
    base_y = layout.row_y(row)
    return [(layout.column_x(col), base_y + layout.column_bob(col)) for col in cols]


def _build_path_positions(layout: _Layout) -> list[tuple[float, float]]:
    """Centre point of every circle, Start first, Finish last - a
    boustrophedon path (left-to-right, then right-to-left, ...) with a
    connector circle bridging each row change, alternating sides. Connector
    height is the midpoint of the actual (bobbing) circles it joins, so the
    trail never has to jump an extra offset right at the connector."""
    positions: list[tuple[float, float]] = []
    row_cache: dict[int, list[tuple[float, float]]] = {}

    def row_positions(row: int) -> list[tuple[float, float]]:
        if row not in row_cache:
            row_cache[row] = _row_positions(layout, row, left_to_right=row % 2 == 0)
        return row_cache[row]

    for row in range(NUM_ROWS):
        this_row = row_positions(row)
        positions.extend(this_row)
        if row < NUM_ROWS - 1:
            side = "right" if row % 2 == 0 else "left"
            x = layout.slot_x(_TOTAL_SLOTS - 1) if side == "right" else layout.slot_x(0)
            y = (this_row[-1][1] + row_positions(row + 1)[0][1]) / 2
            positions.append((x, y))
    return positions


def render_trail_image(trail: WordTrail, page_size: str = "A4") -> Image.Image:
    layout = _layout_for(page_size)
    k = layout.k  # scales the decorative constants below (title size, label
    # offsets, legend spacing) that aren't already part of _Layout.
    scale = SUPERSAMPLE
    img_w, img_h = round(layout.img_width * scale), round(layout.img_height * scale)
    img = Image.new("RGB", (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    def S(v: float) -> float:
        return v * scale

    regular_path, bold_path = get_board_font_paths()
    title_font = ImageFont.truetype(bold_path, int(S(56 * k)))
    subtitle_font = ImageFont.truetype(regular_path, int(S(30 * k)))
    label_font = ImageFont.truetype(regular_path, int(S(24 * k)))
    legend_font = ImageFont.truetype(regular_path, int(S(26 * k)))

    def centered_text(y: float, text: str, font: ImageFont.FreeTypeFont, fill=COLOR_TEXT) -> None:
        box = draw.textbbox((0, 0), text, font=font)
        w = box[2] - box[0]
        draw.text((S(layout.img_width / 2) - w / 2, S(y)), text, font=font, fill=fill)

    centered_text(50 * k, "Word Trail", title_font)
    centered_text(120 * k, f"for {trail.child_name}", subtitle_font, fill=COLOR_MUTED)

    positions = _build_path_positions(layout)
    radius = layout.circle_diameter / 2

    # The connecting trail, drawn first so the circles sit cleanly on top
    # of where it enters/exits each one.
    path_width = S(radius * 0.18)
    for p1, p2 in zip(positions, positions[1:]):
        _draw_wavy_segment(draw, (S(p1[0]), S(p1[1])), (S(p2[0]), S(p2[1])), S(radius), path_width)

    for i, (word, (x, y)) in enumerate(zip(trail.trail, positions)):
        is_start = i == 0
        is_finish = i == len(positions) - 1
        fill = COLOR_START_FILL if is_start else COLOR_FINISH_FILL if is_finish else COLOR_FILL
        draw.ellipse(
            [S(x - radius), S(y - radius), S(x + radius), S(y + radius)],
            fill=fill, outline=COLOR_OUTLINE, width=max(2, int(S(3 * k))),
        )
        font = fit_font(draw, word, bold_path, int(S(34 * k)), int(S(layout.circle_diameter - 30 * k)))
        box = draw.textbbox((0, 0), word, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        draw.text((S(x) - tw / 2, S(y) - th / 2 - box[1]), word, font=font, fill=COLOR_TEXT)

        if is_start:
            label_box = draw.textbbox((0, 0), "Start", font=label_font)
            draw.text((S(x) - (label_box[2] - label_box[0]) / 2, S(y + radius + 10 * k)), "Start", font=label_font, fill=COLOR_MUTED)
        if is_finish:
            label_box = draw.textbbox((0, 0), "Finish", font=label_font)
            draw.text((S(x) - (label_box[2] - label_box[0]) / 2, S(y + radius + 10 * k)), "Finish", font=label_font, fill=COLOR_MUTED)

    legend_top = layout.row_y(NUM_ROWS - 1) + radius + 90 * k
    instructions = (
        "You'll need a die and a counter for each player. Take turns rolling "
        "and moving your counter that many circles along the trail, reading "
        "the word out loud each time you land. First to reach Finish wins!"
    )
    line_y = legend_top
    for line in wrap_text(draw, instructions, legend_font, S(layout.img_width - 2 * layout.margin)):
        draw.text((S(layout.margin), S(line_y)), line, font=legend_font, fill=COLOR_MUTED)
        line_y += 38 * k

    if scale != 1:
        img = img.resize((round(layout.img_width), round(layout.img_height)), Image.LANCZOS)
    return img


def export_word_trail_pdf(trail: WordTrail, output_path: str, page_size: str = "A4") -> None:
    export_full_page_image_pdf(
        render_trail_image(trail, page_size), output_path, title="Word Trail", page_size=page_size
    )


def export_word_trail_docx(trail: WordTrail, output_path: str, page_size: str = "A4") -> None:
    export_full_page_image_docx(render_trail_image(trail, page_size), output_path, page_size=page_size)
