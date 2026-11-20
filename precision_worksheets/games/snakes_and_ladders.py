"""A printable Snakes & Ladders board using the target words.

Standard rules, plus one twist: a handful of squares show one of the
target words instead of a number - land on one and read it out loud; get
it right and take another turn. Everything (board, ladders, snakes, word
squares, instructions) is drawn once as a single image with Pillow, which
both the PDF and Word exporters just place full-page - so the two formats
always look identical.

Placement rules, so the board always makes sense at a glance:
  - ladders and snakes are short-ish (1-4 rows) and mostly upright -
    never a long sideways slide across the whole board;
  - no two ladders/snakes cross or touch, and none starts or ends on the
    same square as another;
  - word squares are only put where no ladder or snake passes over them,
    so a word is never hidden under a snake.
Every board is randomly different (pass a seed to repeat one).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PIL import Image

from ._drawing import export_full_page_image_docx, export_full_page_image_pdf
from ._fun import (
    INK,
    MUTED,
    PASTEL_RAINBOW,
    RAINBOW,
    WHITE,
    Canvas,
    catmull_rom,
    darker,
    draw_dice,
    draw_fun_title,
    draw_legend_row,
    draw_name_banner,
    draw_star,
    draw_word_chips,
    lighter,
    resample_polyline,
)

BOARD_SIZE = 10  # 10 x 10 = 100 squares
N_LADDERS = 6
N_SNAKES = 6
WORD_SQUARE_REPEATS = 2  # each word appears on this many board squares
MAX_ROWS_SPANNED = 4

# Layout, in "logical" pixels (drawn at SUPERSAMPLE x this and downscaled
# for anti-aliased edges on the diagonal ladders and curved snakes).
SUPERSAMPLE = 2
IMG_WIDTH = 1654
IMG_HEIGHT = 2339
CELL_SIZE = 150
BOARD_PIXELS = CELL_SIZE * BOARD_SIZE
BOARD_LEFT = (IMG_WIDTH - BOARD_PIXELS) // 2
BOARD_TOP = 290

COLOR_WORD_SQUARE = (255, 255, 255)
COLOR_GRID = (120, 110, 140)
COLOR_BORDER = INK
COLOR_LADDER = (190, 125, 60)
COLOR_RUNG = (225, 165, 90)
SNAKE_COLORS = [
    ((120, 205, 90), (255, 212, 59)),
    ((255, 120, 150), (255, 220, 120)),
    ((150, 120, 230), (120, 220, 240)),
    ((255, 160, 60), (255, 235, 140)),
    ((70, 185, 230), (200, 240, 140)),
    ((240, 95, 95), (255, 200, 200)),
]
BACKGROUND = (250, 247, 255)


@dataclass
class SnakesAndLaddersBoard:
    child_name: str
    words: list[str]
    ladders: dict[int, int] = field(default_factory=dict)  # start -> end, climb up
    snakes: dict[int, int] = field(default_factory=dict)  # start -> end, slide down
    word_squares: dict[int, str] = field(default_factory=dict)  # square -> word
    seed: int = 0


def _row_col(n: int) -> tuple[int, int]:
    """(row from bottom, column from left) of square n."""
    row, col = divmod(n - 1, BOARD_SIZE)
    if row % 2 == 1:
        col = BOARD_SIZE - 1 - col
    return row, col


def _seg_dist(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.dist(p, (ax + dx * t, ay + dy * t))


def _segments_gap(a1, a2, b1, b2) -> float:
    """Smallest distance between two line segments (0 if they cross)."""
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2 = ccw(a1, a2, b1), ccw(a1, a2, b2)
    d3, d4 = ccw(b1, b2, a1), ccw(b1, b2, a2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(_seg_dist(a1, b1, b2), _seg_dist(a2, b1, b2), _seg_dist(b1, a1, a2), _seg_dist(b2, a1, a2))


def _grid_point(n: int) -> tuple[float, float]:
    """Square n's centre in cell units (x right, y up)."""
    row, col = _row_col(n)
    return (col + 0.5, row + 0.5)


def build_board(child_name: str, words: list[str], seed: int | None = None) -> SnakesAndLaddersBoard:
    """Randomly place ladders, snakes and word squares on a 100-square board."""
    clean_words = [w.strip() for w in words if w.strip()]
    if not clean_words:
        raise ValueError("At least one word is required")

    if seed is None:
        seed = random.randrange(1, 10**9)
    rng = random.Random(seed)
    used: set[int] = {1, 100}
    ladders: dict[int, int] = {}
    snakes: dict[int, int] = {}
    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []

    def place(is_ladder: bool) -> None:
        for _ in range(400):
            if is_ladder:
                start = rng.randint(2, 80)
                rows_up = rng.randint(1, MAX_ROWS_SPANNED)
            else:
                start = rng.randint(21, 99)
                rows_up = -rng.randint(1, MAX_ROWS_SPANNED)
            row, col = _row_col(start)
            end_row = row + rows_up
            if not 0 <= end_row < BOARD_SIZE:
                continue
            # Mostly upright: the sideways shift is at most one more
            # column than the number of rows climbed/slid.
            max_shift = min(2 if is_ladder else 3, abs(rows_up) + 1)
            end_col = col + rng.randint(-max_shift, max_shift)
            if not 0 <= end_col < BOARD_SIZE:
                continue
            end = end_row * BOARD_SIZE + (end_col if end_row % 2 == 0 else BOARD_SIZE - 1 - end_col) + 1
            if end in used or start in used or end in (1, 100):
                continue
            a, b = _grid_point(start), _grid_point(end)
            if any(_segments_gap(a, b, s1, s2) < 0.75 for s1, s2 in segments):
                continue
            used.update((start, end))
            segments.append((a, b))
            (ladders if is_ladder else snakes)[start] = end
            return

    # Interleave so neither kind hogs the good spots.
    for _ in range(max(N_LADDERS, N_SNAKES)):
        if len(ladders) < N_LADDERS:
            place(True)
        if len(snakes) < N_SNAKES:
            place(False)

    # Word squares go only where no ladder/snake passes over them.
    clear = [
        n for n in range(2, 100)
        if n not in used and all(_seg_dist(_grid_point(n), s1, s2) >= 0.62 for s1, s2 in segments)
    ]
    rng.shuffle(clear)
    n_word_squares = min(len(clear), len(clean_words) * WORD_SQUARE_REPEATS)
    word_pool = [clean_words[i % len(clean_words)] for i in range(n_word_squares)]
    rng.shuffle(word_pool)
    # Spread them out: prefer squares not right next to another word square.
    chosen: list[int] = []
    for n in clear:
        if len(chosen) >= n_word_squares:
            break
        if all(math.dist(_grid_point(n), _grid_point(m)) > 1.01 for m in chosen):
            chosen.append(n)
    for n in clear:
        if len(chosen) >= n_word_squares:
            break
        if n not in chosen:
            chosen.append(n)
    word_squares = dict(zip(chosen, word_pool))

    return SnakesAndLaddersBoard(
        child_name=child_name, words=clean_words,
        ladders=ladders, snakes=snakes, word_squares=word_squares, seed=seed,
    )


def _square_center(n: int) -> tuple[int, int]:
    """Pixel centre of square `n` (1-100), numbered boustrophedon-style:
    1-10 left to right along the bottom row, 11-20 right to left, and so on
    up to 100 - the classic Snakes & Ladders layout."""
    idx = n - 1
    row_from_bottom, col_in_row = divmod(idx, BOARD_SIZE)
    if row_from_bottom % 2 == 1:
        col_in_row = BOARD_SIZE - 1 - col_in_row
    row_from_top = BOARD_SIZE - 1 - row_from_bottom
    x = BOARD_LEFT + col_in_row * CELL_SIZE + CELL_SIZE // 2
    y = BOARD_TOP + row_from_top * CELL_SIZE + CELL_SIZE // 2
    return x, y


def _perpendicular(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy) or 1
    return -dy / length, dx / length


def _draw_ladder(c: Canvas, start: tuple[float, float], end: tuple[float, float], k: float = 1.0) -> None:
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    # Extend a little past the square centres so the feet/top sit nicely.
    x1, y1, x2, y2 = x1 - ux * 22 * k, y1 - uy * 22 * k, x2 + ux * 22 * k, y2 + uy * 22 * k
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    px, py = _perpendicular(dx, dy)
    gap = 26 * k
    steps = max(3, int(length // (42 * k)))
    # Soft shadow, then rungs, then rails on top.
    for side in (-1, 1):
        c.line([(x1 + px * gap * side + 6, y1 + py * gap * side + 7), (x2 + px * gap * side + 6, y2 + py * gap * side + 7)],
               fill=(205, 200, 215), width=14 * k)
    for i in range(1, steps):
        t = i / steps
        cx, cy = x1 + dx * t, y1 + dy * t
        seg = [(cx + px * gap, cy + py * gap), (cx - px * gap, cy - py * gap)]
        c.line(seg, fill=darker(COLOR_RUNG, 0.6), width=11 * k)
        c.line(seg, fill=COLOR_RUNG, width=6 * k)
    for side in (-1, 1):
        rail = [(x1 + px * gap * side, y1 + py * gap * side), (x2 + px * gap * side, y2 + py * gap * side)]
        c.line(rail, fill=darker(COLOR_LADDER, 0.55), width=16 * k)
        c.line(rail, fill=COLOR_LADDER, width=10 * k)


def _draw_snake(c: Canvas, head: tuple[float, float], tail: tuple[float, float], colors, rng: random.Random) -> None:
    body_col, stripe_col = colors
    x1, y1 = head
    x2, y2 = tail
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    px, py = _perpendicular(dx, dy)
    waves = max(2, round(length / 170))
    amp = min(55, length * 0.12) * rng.choice([-1, 1])
    ctrl = [(x1, y1)]
    for k in range(1, waves * 2):
        t = k / (waves * 2)
        off = amp * (1 if k % 2 else -1)
        ctrl.append((x1 + dx * t + px * off, y1 + dy * t + py * off))
    ctrl.append((x2, y2))
    body = resample_polyline(catmull_rom(ctrl, 20), 3)
    n = len(body)
    w_head, w_tail = 24, 6

    def width_at(i: int) -> float:
        return w_head + (w_tail - w_head) * (i / max(1, n - 1)) ** 1.3

    # Shadow, outline, body with stripes.
    for i, (bx, by) in enumerate(body):
        c.circle(bx + 6, by + 7, width_at(i), fill=(205, 200, 215))
    for i, (bx, by) in enumerate(body):
        c.circle(bx, by, width_at(i) + 3.5, fill=darker(body_col, 0.5))
    dist = 0.0
    for i, (bx, by) in enumerate(body):
        if i:
            dist += math.dist(body[i - 1], body[i])
        stripe = int(dist // 26) % 2 == 1
        c.circle(bx, by, width_at(i), fill=stripe_col if stripe and i > 8 else body_col)
    # Belly shine along one side.
    shine = [(bx + px * width_at(i) * 0.35, by + py * width_at(i) * 0.35) for i, (bx, by) in enumerate(body[6: n // 2])]
    if len(shine) > 2:
        c.line(shine, fill=lighter(body_col, 0.55), width=5)

    # Head, pointing away from the body.
    hx, hy = body[0]
    nx, ny = body[min(8, n - 1)]
    ux, uy = hx - nx, hy - ny
    ul = math.hypot(ux, uy) or 1
    ux, uy = ux / ul, uy / ul
    hpx, hpy = -uy, ux
    cx, cy = hx + ux * 10, hy + uy * 10
    # Forked tongue.
    t0 = (cx + ux * 30, cy + uy * 30)
    t1 = (cx + ux * 48, cy + uy * 48)
    c.line([t0, t1], fill=(220, 40, 60), width=5)
    for s in (-1, 1):
        c.line([t1, (t1[0] + ux * 12 + hpx * 9 * s, t1[1] + uy * 12 + hpy * 9 * s)], fill=(220, 40, 60), width=4)
    c.circle(cx, cy, 33, fill=darker(body_col, 0.5))
    c.circle(cx, cy, 30, fill=body_col)
    for s in (-1, 1):
        ex, ey = cx + hpx * 14 * s + ux * 6, cy + hpy * 14 * s + uy * 6
        c.circle(ex, ey, 10, fill=WHITE, outline=INK, width=2)
        c.circle(ex + ux * 3, ey + uy * 3, 5, fill=INK)
    for s in (-1, 1):
        c.circle(cx - ux * 10 + hpx * 20 * s, cy - uy * 10 + hpy * 20 * s, 5, fill=(255, 150, 160))


def render_board_image(board: SnakesAndLaddersBoard) -> Image.Image:
    """Draw the full board (title, grid, ladders, snakes, legend) as one image."""
    rng = random.Random(board.seed * 13 + 5)
    c = Canvas(IMG_WIDTH, IMG_HEIGHT, background=BACKGROUND, scale=SUPERSAMPLE)
    c.rect(18, 18, IMG_WIDTH - 18, IMG_HEIGHT - 18, outline=(225, 215, 245), width=14, radius=40)

    draw_fun_title(c, "Snakes & Ladders", 100, 92, rng=rng)
    draw_name_banner(c, 205, board.child_name)

    number_font = c.font(26)
    # Board shadow.
    c.rect(BOARD_LEFT + 10, BOARD_TOP + 12, BOARD_LEFT + BOARD_PIXELS + 10, BOARD_TOP + BOARD_PIXELS + 12,
           fill=(215, 205, 235), radius=26)
    for row in range(BOARD_SIZE):
        base = PASTEL_RAINBOW[(BOARD_SIZE - 1 - row) % len(PASTEL_RAINBOW)]
        for col in range(BOARD_SIZE):
            n = _square_number_at(row, col)
            x0 = BOARD_LEFT + col * CELL_SIZE
            y0 = BOARD_TOP + row * CELL_SIZE
            fill = base if (row + col) % 2 == 0 else lighter(base, 0.55)
            c.rect(x0, y0, x0 + CELL_SIZE, y0 + CELL_SIZE, fill=fill, outline=COLOR_GRID, width=1.5)
            if n in board.word_squares:
                c.rect(x0 + 9, y0 + 9, x0 + CELL_SIZE - 9, y0 + CELL_SIZE - 9, fill=COLOR_WORD_SQUARE,
                       outline=darker(base, 0.55), width=5, radius=20)
                c.word(x0 + CELL_SIZE / 2, y0 + CELL_SIZE / 2 + 8, board.word_squares[n], 44, CELL_SIZE - 34)
                draw_star(c, x0 + 26, y0 + 26, 17, width=2)
            elif n in (1, 100):
                label = "START" if n == 1 else "FINISH"
                col_fill = (130, 215, 120) if n == 1 else (255, 205, 60)
                c.rect(x0 + 9, y0 + 9, x0 + CELL_SIZE - 9, y0 + CELL_SIZE - 9, fill=col_fill,
                       outline=darker(col_fill, 0.5), width=5, radius=20)
                c.word(x0 + CELL_SIZE / 2, y0 + CELL_SIZE / 2 + 14, label, 32, CELL_SIZE - 30, fill=WHITE,
                       halo=darker(col_fill, 0.45))
                c.text_center(x0 + CELL_SIZE / 2, y0 + 34, str(n), number_font, fill=INK)
            else:
                c.text(x0 + 10, y0 + 6, str(n), number_font, fill=darker(base, 0.45))

    def centre(n: int) -> tuple[float, float]:
        return _square_center(n)

    for start, end in board.ladders.items():
        _draw_ladder(c, centre(start), centre(end))
    for i, (start, end) in enumerate(board.snakes.items()):
        _draw_snake(c, centre(start), centre(end), SNAKE_COLORS[i % len(SNAKE_COLORS)], rng)

    c.rect(BOARD_LEFT, BOARD_TOP, BOARD_LEFT + BOARD_PIXELS, BOARD_TOP + BOARD_PIXELS, outline=COLOR_BORDER, width=5, radius=6)

    # Footer: the words, then how to play.
    chips_y = BOARD_TOP + BOARD_PIXELS + 72
    draw_word_chips(c, chips_y, board.words, max_width=IMG_WIDTH - 260, backing=WHITE, backing_outline=(225, 215, 245))
    top, bottom = chips_y + 62, IMG_HEIGHT - 60
    x0, x1 = 70, IMG_WIDTH - 70
    c.rect(x0, top + 6, x1, bottom + 6, fill=(220, 212, 240), radius=28)
    c.rect(x0, top, x1, bottom, fill=WHITE, outline=INK, width=4, radius=28)
    c.text_center(IMG_WIDTH / 2, top + 40, "How to play", c.font(36), fill=INK)
    body = c.font(27, bold=False)
    ry = top + 118
    step = 86
    col2 = IMG_WIDTH / 2 + 20

    def word_icon(cc, cx, cy, s):
        cc.rect(cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2, fill=WHITE, outline=darker(PASTEL_RAINBOW[0], 0.55), width=4, radius=10)
        draw_star(cc, cx, cy, s * 0.3, width=2)

    def ladder_icon(cc, cx, cy, s):
        _draw_ladder(cc, (cx - s * 0.08, cy + s * 0.22), (cx + s * 0.08, cy - s * 0.22), k=0.42)

    def snake_icon(cc, cx, cy, s):
        for i in range(12):
            t = i / 11
            cc.circle(cx - s * 0.4 + s * 0.8 * t, cy + math.sin(t * 2 * math.pi) * s * 0.18, 9 - 5 * t, fill=SNAKE_COLORS[0][0])
        cc.circle(cx - s * 0.42, cy, 11, fill=SNAKE_COLORS[0][0], outline=darker(SNAKE_COLORS[0][0], 0.5), width=2)
        cc.circle(cx - s * 0.45, cy - 3, 3, fill=INK)

    draw_legend_row(c, x0 + 30, ry, lambda cc, cx, cy, s: draw_dice(cc, cx, cy, s * 0.85, 4), "Roll the die and move.", body, icon_size=54)
    draw_legend_row(c, x0 + 30, ry + step, word_icon, "Word square? Read it - roll again!", body, icon_size=54)
    draw_legend_row(c, col2, ry, ladder_icon, "Bottom of a ladder? Climb up!", body, icon_size=54)
    draw_legend_row(c, col2, ry + step, snake_icon, "Snake's head? Slide down to its tail.", body, icon_size=54)
    c.text_center(IMG_WIDTH / 2, bottom - 40, "First one to reach 100 wins!", c.font(28), fill=MUTED)
    return c.finish()


def _square_number_at(row: int, col: int) -> int:
    """Inverse of _square_center: the square number drawn at grid (row, col),
    where row 0 is the top row and col 0 is the left column."""
    row_from_bottom = BOARD_SIZE - 1 - row
    col_in_row = col if row_from_bottom % 2 == 0 else BOARD_SIZE - 1 - col
    return row_from_bottom * BOARD_SIZE + col_in_row + 1


def export_board_pdf(board: SnakesAndLaddersBoard, output_path: str) -> None:
    export_full_page_image_pdf(render_board_image(board), output_path, title="Snakes and Ladders")


def export_board_docx(board: SnakesAndLaddersBoard, output_path: str) -> None:
    export_full_page_image_docx(render_board_image(board), output_path)
