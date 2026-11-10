"""Shared playful-drawing helpers for the colourful board games.

Everything here works in "logical" A4 pixels (1654 x 2339, roughly 200dpi)
and a `Canvas` scales to the supersampled image for us, so board code can
think in page coordinates and never has to remember to multiply by the
supersample factor.

Nothing here uses emoji or icon fonts - every little picture (stars,
palm trees, rockets, ...) is drawn from plain shapes with Pillow, so the
boards look the same on every PC and print cleanly.
"""

from __future__ import annotations

import math
import random
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont

from ..fonts import get_board_font_paths
from ._drawing import fit_font, wrap_text

Point = tuple[float, float]
Color = tuple[int, int, int]

PAGE_W = 1654
PAGE_H = 2339
SUPERSAMPLE = 2

INK = (45, 40, 60)
MUTED = (95, 90, 110)
WHITE = (255, 255, 255)

# Bright-but-printable colours used across the boards (title letters, word
# chips, rainbow tiles...). Ordered so neighbours contrast well.
RAINBOW = [
    (255, 99, 99),    # red
    (255, 165, 60),   # orange
    (255, 212, 59),   # yellow
    (120, 205, 90),   # green
    (70, 185, 230),   # blue
    (150, 120, 230),  # purple
    (255, 120, 190),  # pink
]

PASTEL_RAINBOW = [
    (255, 196, 196),
    (255, 220, 175),
    (255, 240, 170),
    (204, 238, 186),
    (186, 226, 247),
    (214, 202, 247),
    (255, 205, 230),
]


def darker(color: Color, factor: float = 0.65) -> Color:
    return tuple(max(0, int(c * factor)) for c in color)  # type: ignore[return-value]


def lighter(color: Color, factor: float = 0.5) -> Color:
    return tuple(int(c + (255 - c) * factor) for c in color)  # type: ignore[return-value]


class Canvas:
    """A supersampled Pillow image you draw on in logical page pixels."""

    def __init__(self, width: int = PAGE_W, height: int = PAGE_H, background: Color = WHITE, scale: int = SUPERSAMPLE):
        self.width = width
        self.height = height
        self.k = scale
        self.img = Image.new("RGB", (round(width * scale), round(height * scale)), background)
        self.draw = ImageDraw.Draw(self.img)
        self.regular_path, self.bold_path = get_board_font_paths()

    # -- coordinate helpers -------------------------------------------------
    def s(self, v: float) -> float:
        return v * self.k

    def sp(self, p: Point) -> Point:
        return (p[0] * self.k, p[1] * self.k)

    def w(self, v: float) -> int:
        """A line width in logical px, never thinner than 1 real px."""
        return max(1, int(round(v * self.k)))

    def font(self, size: float, bold: bool = True) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(self.bold_path if bold else self.regular_path, max(4, int(size * self.k)))

    # -- shapes ---------------------------------------------------------------
    def ellipse(self, cx: float, cy: float, rx: float, ry: float | None = None, fill=None, outline=None, width: float = 0) -> None:
        ry = rx if ry is None else ry
        self.draw.ellipse(
            [self.s(cx - rx), self.s(cy - ry), self.s(cx + rx), self.s(cy + ry)],
            fill=fill, outline=outline, width=self.w(width) if outline is not None and width else 0,
        )

    def circle(self, cx: float, cy: float, r: float, fill=None, outline=None, width: float = 0) -> None:
        self.ellipse(cx, cy, r, r, fill=fill, outline=outline, width=width)

    def rect(self, x0: float, y0: float, x1: float, y1: float, fill=None, outline=None, width: float = 0, radius: float = 0) -> None:
        box = [self.s(x0), self.s(y0), self.s(x1), self.s(y1)]
        kw = dict(fill=fill, outline=outline, width=self.w(width) if outline is not None and width else 0)
        if radius:
            self.draw.rounded_rectangle(box, radius=self.s(radius), **kw)
        else:
            self.draw.rectangle(box, **kw)

    def polygon(self, points: Sequence[Point], fill=None, outline=None, width: float = 0) -> None:
        pts = [self.sp(p) for p in points]
        self.draw.polygon(pts, fill=fill, outline=outline, width=self.w(width) if outline is not None and width else 0)

    def line(self, points: Sequence[Point], fill, width: float, round_caps: bool = True) -> None:
        pts = [self.sp(p) for p in points]
        if len(pts) < 2:
            return
        self.draw.line(pts, fill=fill, width=self.w(width), joint="curve")
        if round_caps:
            r = width / 2
            for p in (points[0], points[-1]):
                self.circle(p[0], p[1], r, fill=fill)

    def dashed_line(self, points: Sequence[Point], fill, width: float, dash: float, gap: float) -> None:
        """A dashed polyline (dash/gap measured along the path)."""
        for seg in split_dashes(points, dash, gap):
            self.line(seg, fill, width)

    def dotted_line(self, points: Sequence[Point], fill, radius: float, spacing: float) -> None:
        for p in resample_polyline(points, spacing):
            self.circle(p[0], p[1], radius, fill=fill)

    def arc_band(self, points: Sequence[Point], fill, width: float) -> None:
        """A thick smooth band following `points` (drawn as overlapping
        circles - Pillow's thick lines get notchy on tight curves)."""
        r = width / 2
        for p in resample_polyline(points, max(2.0, r / 3)):
            self.circle(p[0], p[1], r, fill=fill)

    # -- text -----------------------------------------------------------------
    def text_center(self, cx: float, cy: float, text: str, font: ImageFont.FreeTypeFont, fill=INK,
                    stroke: float = 0, stroke_fill=None) -> None:
        box = self.draw.textbbox((0, 0), text, font=font, stroke_width=self.w(stroke) if stroke else 0)
        tw, th = box[2] - box[0], box[3] - box[1]
        self.draw.text(
            (self.s(cx) - tw / 2 - box[0], self.s(cy) - th / 2 - box[1]), text, font=font, fill=fill,
            stroke_width=self.w(stroke) if stroke else 0, stroke_fill=stroke_fill,
        )

    def text(self, x: float, y: float, text: str, font: ImageFont.FreeTypeFont, fill=INK) -> None:
        self.draw.text((self.s(x), self.s(y)), text, font=font, fill=fill)

    def text_width(self, text: str, font: ImageFont.FreeTypeFont) -> float:
        box = self.draw.textbbox((0, 0), text, font=font)
        return (box[2] - box[0]) / self.k

    def fit_word_font(self, word: str, max_size: float, max_width: float, min_size: float = 14) -> ImageFont.FreeTypeFont:
        return fit_font(self.draw, word, self.bold_path, int(self.s(max_size)), int(self.s(max_width)), int(self.s(min_size)))

    def word(self, cx: float, cy: float, word: str, max_size: float, max_width: float, fill=INK, halo: Color | None = None) -> None:
        """A target word, as big as fits, centred - optionally with a soft
        outline 'halo' so it stays crisp over a busy tile."""
        font = self.fit_word_font(word, max_size, max_width)
        if halo is not None:
            self.text_center(cx, cy, word, font, fill=fill, stroke=max(2, font.size / self.k * 0.08), stroke_fill=halo)
        else:
            self.text_center(cx, cy, word, font, fill=fill)

    def wrapped(self, x: float, y: float, text: str, font: ImageFont.FreeTypeFont, max_width: float,
                line_height: float, fill=MUTED) -> float:
        for line in wrap_text(self.draw, text, font, self.s(max_width)):
            self.text(x, y, line, font, fill)
            y += line_height
        return y

    def finish(self) -> Image.Image:
        if self.k == 1:
            return self.img
        return self.img.resize((self.width, self.height), Image.LANCZOS)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def catmull_rom(points: Sequence[Point], samples_per_segment: int = 24) -> list[Point]:
    """A smooth curve passing through every one of `points`."""
    if len(points) < 3:
        return list(points)
    pts = [points[0]] + list(points) + [points[-1]]
    out: list[Point] = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for j in range(samples_per_segment):
            t = j / samples_per_segment
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(points[-1])
    return out


def polyline_length(points: Sequence[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def resample_polyline(points: Sequence[Point], spacing: float) -> list[Point]:
    """Points every `spacing` px along the polyline (first point included)."""
    if not points:
        return []
    out = [points[0]]
    carry = 0.0
    for a, b in zip(points, points[1:]):
        seg = math.dist(a, b)
        if seg == 0:
            continue
        d = spacing - carry
        while d <= seg:
            t = d / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            d += spacing
        carry = seg - (d - spacing)
    return out


def points_along(points: Sequence[Point], n: int) -> list[Point]:
    """`n` points spread evenly (by arc length) from the first to the last
    point of the polyline, both ends included."""
    total = polyline_length(points)
    if n < 2 or total == 0:
        return [points[0]] * max(n, 1)
    spacing = total / (n - 1)
    pts = resample_polyline(points, spacing)
    # Floating point can leave us one short / with a near-duplicate end.
    pts = pts[: n - 1] + [points[-1]]
    while len(pts) < n:
        pts.insert(-1, points[-1])
    return pts


def sub_polyline(points: Sequence[Point], a: Point, b: Point) -> list[Point]:
    """The part of the polyline between the samples closest to a and b."""
    ia = min(range(len(points)), key=lambda i: math.dist(points[i], a))
    ib = min(range(len(points)), key=lambda i: math.dist(points[i], b))
    if ia > ib:
        ia, ib = ib, ia
    return list(points[ia: ib + 1])


def split_dashes(points: Sequence[Point], dash: float, gap: float) -> list[list[Point]]:
    dense = resample_polyline(points, 2.0)
    segments: list[list[Point]] = []
    period = dash + gap
    dist = 0.0
    current: list[Point] = []
    prev = dense[0] if dense else None
    for p in dense:
        if prev is not None:
            dist += math.dist(prev, p)
        prev = p
        if dist % period < dash:
            current.append(p)
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return [s for s in segments if len(s) > 1]


def min_nonadjacent_gap(points: Sequence[Point], skip: int = 1) -> float:
    """Smallest distance between two points more than `skip` apart in the
    sequence - used to check a generated trail doesn't fold onto itself."""
    best = float("inf")
    for i in range(len(points)):
        for j in range(i + skip + 1, len(points)):
            best = min(best, math.dist(points[i], points[j]))
    return best


# ---------------------------------------------------------------------------
# Little pictures
# ---------------------------------------------------------------------------

def star_points(cx: float, cy: float, r_outer: float, r_inner: float | None = None, n: int = 5, rotation: float = -90) -> list[Point]:
    r_inner = r_outer * 0.45 if r_inner is None else r_inner
    pts = []
    for i in range(n * 2):
        r = r_outer if i % 2 == 0 else r_inner
        a = math.radians(rotation + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def draw_star(c: Canvas, cx: float, cy: float, r: float, fill=(255, 212, 59), outline=INK, width: float = 3, rotation: float = -90) -> None:
    c.polygon(star_points(cx, cy, r, rotation=rotation), fill=fill, outline=outline, width=width)


def draw_heart(c: Canvas, cx: float, cy: float, r: float, fill=(255, 99, 130), outline=INK, width: float = 3) -> None:
    pts = []
    for i in range(60):
        t = 2 * math.pi * i / 60
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * r / 17, cy + y * r / 17))
    c.polygon(pts, fill=fill, outline=outline, width=width)


def draw_cloud(c: Canvas, cx: float, cy: float, size: float, fill=WHITE, outline=(170, 190, 215)) -> None:
    bumps = [(-0.55, 0.1, 0.38), (-0.2, -0.18, 0.5), (0.25, -0.1, 0.45), (0.6, 0.12, 0.34), (0.05, 0.18, 0.42)]
    for dx, dy, r in bumps:
        c.circle(cx + dx * size, cy + dy * size, r * size + 3, fill=outline)
    for dx, dy, r in bumps:
        c.circle(cx + dx * size, cy + dy * size, r * size, fill=fill)


def draw_flower(c: Canvas, cx: float, cy: float, r: float, petal: Color, centre: Color = (255, 212, 59)) -> None:
    c.line([(cx, cy + r * 0.6), (cx, cy + r * 2.4)], fill=(90, 170, 80), width=r * 0.25)
    c.ellipse(cx + r * 0.45, cy + r * 1.7, r * 0.45, r * 0.2, fill=(110, 190, 95))
    for i in range(5):
        a = math.radians(i * 72 - 90)
        c.circle(cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62, r * 0.5, fill=petal, outline=darker(petal), width=2)
    c.circle(cx, cy, r * 0.42, fill=centre, outline=darker(centre), width=2)


def draw_dice(c: Canvas, cx: float, cy: float, size: float, value: int = 5, fill=WHITE, rotation_hint: float = 0) -> None:
    h = size / 2
    c.rect(cx - h, cy - h, cx + h, cy + h, fill=fill, outline=INK, width=3, radius=size * 0.18)
    pip = size * 0.09
    o = size * 0.26
    layouts = {
        1: [(0, 0)],
        2: [(-o, -o), (o, o)],
        3: [(-o, -o), (0, 0), (o, o)],
        4: [(-o, -o), (o, -o), (-o, o), (o, o)],
        5: [(-o, -o), (o, -o), (0, 0), (-o, o), (o, o)],
        6: [(-o, -o), (o, -o), (-o, 0), (o, 0), (-o, o), (o, o)],
    }
    for dx, dy in layouts[value]:
        c.circle(cx + dx, cy + dy, pip, fill=INK)


def draw_arrow(c: Canvas, x0: float, y: float, length: float, color: Color, forwards: bool = True, thickness: float = 14) -> None:
    """A chunky left/right arrow (forwards = pointing right)."""
    d = 1 if forwards else -1
    head = thickness * 1.8
    tip_x = x0 + d * length / 2
    tail_x = x0 - d * length / 2
    neck_x = tip_x - d * head
    c.line([(tail_x, y), (neck_x, y)], fill=color, width=thickness)
    c.polygon([(tip_x, y), (neck_x, y - head * 0.8), (neck_x, y + head * 0.8)], fill=color)


# ---------------------------------------------------------------------------
# Titles / headers / footers shared by every colourful board
# ---------------------------------------------------------------------------

def draw_fun_title(c: Canvas, text: str, cy: float, size: float, colors: Sequence[Color] = RAINBOW,
                   rng: random.Random | None = None, outline: Color = INK) -> None:
    """A bouncy title: every letter its own colour, slightly tilted and
    bobbing, with a thick dark outline so it pops (and still reads when
    printed in greyscale)."""
    rng = rng or random.Random(0)
    font = c.font(size)
    stroke = max(3, size * 0.09)
    letter_imgs = []
    total_w = 0.0
    spacing = size * 0.04
    color_i = rng.randrange(len(colors))
    for ch in text:
        if ch == " ":
            letter_imgs.append(None)
            total_w += size * 0.32
            continue
        box = c.draw.textbbox((0, 0), ch, font=font, stroke_width=c.w(stroke))
        w, h = box[2] - box[0], box[3] - box[1]
        pad = int(c.s(size * 0.25))
        tile = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        color = colors[color_i % len(colors)]
        color_i += 1
        # A drop "shadow" a few px down-right, then the letter.
        off = c.s(size * 0.05)
        td.text((pad - box[0] + off, pad - box[1] + off), ch, font=font, fill=darker(outline, 1.0),
                stroke_width=c.w(stroke), stroke_fill=outline)
        td.text((pad - box[0], pad - box[1]), ch, font=font, fill=color, stroke_width=c.w(stroke), stroke_fill=outline)
        tile = tile.rotate(rng.uniform(-9, 9), resample=Image.BICUBIC, expand=False)
        letter_imgs.append((tile, w / c.k, pad / c.k))
        total_w += w / c.k + spacing

    x = (c.width - total_w) / 2
    for i, item in enumerate(letter_imgs):
        if item is None:
            x += size * 0.32
            continue
        tile, w, pad = item
        bob = math.sin(i * 1.3 + rng.uniform(0, 0.6)) * size * 0.06
        c.img.paste(tile, (int(c.s(x - pad)), int(c.s(cy - tile.height / c.k / 2 + bob))), tile)
        x += w + spacing


def draw_name_banner(c: Canvas, cy: float, child_name: str, fill: Color = (255, 255, 255), outline: Color = INK) -> None:
    """A ribbon-style banner under the title reading 'Player: <name>'
    (or a blank write-in line if there is no name)."""
    label = f"Player: {child_name}" if child_name.strip() else "Player: ______________"
    font = c.font(30)
    tw = c.text_width(label, font)
    half = tw / 2 + 40
    cx = c.width / 2
    h = 30
    tail = 28
    # Ribbon tails
    for d in (-1, 1):
        x_in = cx + d * (half - 10)
        x_out = cx + d * (half + tail)
        c.polygon([(x_in, cy - h + 12), (x_out, cy - h + 12), (x_out - d * 14, cy + 6), (x_out, cy + h + 12), (x_in, cy + h + 12)],
                  fill=darker(fill, 0.85), outline=outline, width=3)
    c.rect(cx - half, cy - h, cx + half, cy + h, fill=fill, outline=outline, width=3, radius=12)
    c.text_center(cx, cy, label, font, fill=INK)


def draw_word_chips(c: Canvas, cy: float, words: Sequence[str], label: str = "Our words:",
                    colors: Sequence[Color] = PASTEL_RAINBOW, max_width: float | None = None,
                    backing: Color | None = None, backing_outline: Color | None = None) -> None:
    """A single row of rounded, coloured 'chips', one per target word, so
    the grown-up can see at a glance which words are on the board. The
    text shrinks as needed so the row always fits in `max_width` (it never
    wraps onto a second row and spills into whatever is below it).
    `backing` draws a rounded strip behind the whole row."""
    max_width = max_width or c.width - 160
    size = 30.0
    while True:
        label_font = c.font(size * 0.93)
        chip_font = c.font(size)
        h = size * 1.7
        gap = size * 0.5
        pad = size * 1.3
        chips = [(w, c.text_width(w, chip_font) + pad) for w in words]
        label_w = c.text_width(label, label_font)
        total = label_w + gap + sum(wd for _, wd in chips) + gap * (len(chips) - 1)
        if total <= max_width or size <= 12:
            break
        size -= 1
    x = (c.width - total) / 2
    if backing is not None:
        c.rect(x - 36, cy - h / 2 - 12, x + total + 36, cy + h / 2 + 12, fill=backing, outline=backing_outline,
               width=3 if backing_outline else 0, radius=h / 2 + 12)
    c.text_center(x + label_w / 2, cy, label, label_font, fill=MUTED)
    x += label_w + gap
    for i, (word, wd) in enumerate(chips):
        col = colors[i % len(colors)]
        c.rect(x, cy - h / 2, x + wd, cy + h / 2, fill=col, outline=darker(col, 0.55), width=3, radius=h / 2)
        c.text_center(x + wd / 2, cy, word, chip_font, fill=INK)
        x += wd + gap


def draw_legend_row(c: Canvas, x: float, cy: float, icon_fn, text: str, font, icon_size: float = 46) -> None:
    """One 'icon - explanation' line of a How-to-play box."""
    icon_fn(c, x + icon_size / 2, cy, icon_size)
    c.text(x + icon_size + 22, cy - font.size / c.k * 0.62, text, font, fill=INK)


def far_enough(p: Point, others: Iterable[tuple[Point, float]], r: float) -> bool:
    return all(math.dist(p, q) >= r + qr for q, qr in others)


def scatter(rng: random.Random, box: tuple[float, float, float, float], n: int, radius: float,
            avoid: list[tuple[Point, float]], tries: int = 400) -> list[Point]:
    """Up to `n` random points inside `box`, each at least `radius` clear of
    everything in `avoid` (and of each other) - for sprinkling decorations
    into the empty parts of a board."""
    x0, y0, x1, y1 = box
    placed: list[Point] = []
    avoid = list(avoid)
    for _ in range(tries):
        if len(placed) >= n:
            break
        p = (rng.uniform(x0 + radius, x1 - radius), rng.uniform(y0 + radius, y1 - radius))
        if far_enough(p, avoid, radius):
            placed.append(p)
            avoid.append((p, radius))
    return placed
