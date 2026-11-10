"""Colourful 'roll and read' adventure boards.

Each board is a winding path of stepping-stone spaces from START to
FINISH. Most spaces show one of the target words (read it out loud when
you land); a few are special "bonus" spaces that help you along and
"oops" spaces that set you back - always by an amount that lands on an
ordinary word space, so the rules never chain or contradict each other.

Four themes, each with its own picture style, decorations and special
spaces:

  treasure  - Treasure Island: stepping stones across a sandy island in
              the sea, gold coins and grabby crabs, a treasure chest at
              the end.
  space     - Space Race: hop from planet to planet, rocket boosts and
              black holes, land on the Moon.
  rainbow   - Rainbow Swirl: a spiral track winding into a golden star,
              rainbows and rain clouds.
  pond      - Froggy Pond: lily pads across a pond, dragonflies and
              splashes, hop home to the big flower pad.

Every board is different: the path's shape (where it starts, how it
wiggles, how many spaces it has), the order of the words, where the
special spaces fall and where the decorations go are all randomised
from the board's seed. Pass the same seed to get the same board again.

The words are whatever the caller passes in - any number of them, any
length (long words just get a smaller font to fit their space).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

from PIL import Image

from ..generator import generate_word_grid
from ._drawing import export_full_page_images_docx, export_full_page_images_pdf
from ._fun import (
    INK,
    MUTED,
    PAGE_H,
    PAGE_W,
    PASTEL_RAINBOW,
    RAINBOW,
    WHITE,
    Canvas,
    Point,
    catmull_rom,
    darker,
    draw_cloud,
    draw_dice,
    draw_flower,
    draw_fun_title,
    draw_legend_row,
    draw_name_banner,
    draw_star,
    draw_word_chips,
    lighter,
    min_nonadjacent_gap,
    points_along,
    resample_polyline,
    scatter,
    star_points,
)

# Page regions (logical px on an A4-shaped page).
TITLE_Y = 105
BANNER_Y = 215
BOARD_BOX = (70.0, 290.0, PAGE_W - 70.0, 1905.0)
CHIPS_Y = 1960
LEGEND_TOP = 2025
LEGEND_BOTTOM = PAGE_H - 40

START = "start"
FINISH = "finish"
WORD = "word"
BONUS = "bonus"
HAZARD = "hazard"


@dataclass(frozen=True)
class ThemeInfo:
    key: str
    title: str
    shape: str  # "rows" or "spiral"
    tile_radius: float
    bonus_label: str  # short, written on the space itself
    hazard_label: str
    bonus_rule: str  # longer, for the How to play box
    hazard_rule: str
    bonus_move: int  # spaces moved forward when landing on a bonus (0 = roll again)
    hazard_move: int  # spaces moved back when landing on a hazard


THEMES: dict[str, ThemeInfo] = {
    "treasure": ThemeInfo(
        "treasure", "Treasure Island", "rows", 92,
        "Roll again!", "Back 2",
        "Gold coin! Roll again.", "A crab pinched you! Go back 2.",
        0, 2,
    ),
    "space": ThemeInfo(
        "space", "Space Race", "rows", 92,
        "Zoom +2", "Back 2",
        "Rocket boost! Zoom forward 2.", "Black hole! Get sucked back 2.",
        2, 2,
    ),
    "rainbow": ThemeInfo(
        "rainbow", "Rainbow Swirl", "spiral", 80,
        "Roll again!", "Back 2",
        "Rainbow! Roll again.", "Rain cloud! Hide back 2 spaces.",
        0, 2,
    ),
    "pond": ThemeInfo(
        "pond", "Froggy Pond", "rows", 90,
        "Hop +2", "Back 2",
        "Dragonfly! Hop forward 2.", "Splash! You fell in - go back 2.",
        2, 2,
    ),
}

THEME_CHOICES = list(THEMES)


@dataclass
class Space:
    kind: str
    word: str = ""


@dataclass
class AdventureBoard:
    theme: str
    child_name: str
    words: list[str]
    seed: int
    spaces: list[Space]
    positions: list[Point]  # centre of each space, in path order
    radii: list[float]  # radius of each space
    path: list[Point] = field(default_factory=list)  # the smooth curve the spaces sit on

    @property
    def info(self) -> ThemeInfo:
        return THEMES[self.theme]


# ---------------------------------------------------------------------------
# Path generation
# ---------------------------------------------------------------------------

def _rows_path(rng: random.Random, r: float) -> list[Point]:
    """A meandering back-and-forth path: a random number of rows, random
    wobble in each row, random start corner."""
    x0, y0, x1, y1 = BOARD_BOX
    rows = rng.choice([4, 5, 5])
    left, right = x0 + r + 10, x1 - r - 10
    top, bottom = y0 + r + 10, y1 - r - 10
    gap = (bottom - top) / (rows - 1)
    turn = gap / 2
    wobble = min(gap * 0.13, gap - 2.3 * r) if gap > 2.3 * r else 0

    ctrl: list[Point] = []
    for row in range(rows):
        y = top + row * gap
        n = rng.choice([4, 5])
        xs = [left + turn * 0.9 + (right - left - 1.8 * turn) * i / (n - 1) for i in range(n)]
        if row % 2:
            xs.reverse()
        for i, x in enumerate(xs):
            jx = rng.uniform(-35, 35) if 0 < i < n - 1 else 0
            ctrl.append((x + jx, y + rng.uniform(-wobble, wobble)))
        if row < rows - 1:
            side = right if row % 2 == 0 else left
            ctrl.append((side, y + gap / 2 + rng.uniform(-gap * 0.06, gap * 0.06)))

    flip_x = rng.random() < 0.5
    flip_y = rng.random() < 0.5
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ctrl = [((2 * cx - x) if flip_x else x, (2 * cy - y) if flip_y else y) for x, y in ctrl]
    curve = catmull_rom(ctrl, 30)
    # The smoothed curve bulges out a little at the turns; squeeze it back
    # so every space stays on the page.
    return _fit_into(curve, (x0 + r + 6, y0 + r + 6, x1 - r - 6, y1 - r - 6))


def _fit_into(points: list[Point], box: tuple[float, float, float, float]) -> list[Point]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
    tx0, ty0, tx1, ty1 = box
    sx = (tx1 - tx0) / (bx1 - bx0) if bx1 > bx0 else 1
    sy = (ty1 - ty0) / (by1 - by0) if by1 > by0 else 1
    return [(tx0 + (x - bx0) * sx, ty0 + (y - by0) * sy) for x, y in points]


def _spiral_path(rng: random.Random, r: float) -> list[Point]:
    """An oval spiral from the outside in, starting at a random angle and
    turning either way, finishing with a short run into the very centre
    (where the big FINISH star sits)."""
    x0, y0, x1, y1 = BOARD_BOX
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + 10
    rx_max = (x1 - x0) / 2 - r - 12
    ry_max = (y1 - y0) / 2 - r - 12
    turns = rng.uniform(1.85, 2.2)
    start = rng.uniform(0, 2 * math.pi)
    direction = rng.choice([-1, 1])
    end_frac = rng.uniform(0.36, 0.4)
    pts = []
    steps = 1200
    for i in range(steps + 1):
        t = i / steps
        frac = 1 - t * (1 - end_frac)
        a = start + direction * t * turns * 2 * math.pi
        pts.append((cx + rx_max * frac * math.cos(a), cy + ry_max * frac * math.sin(a)))
    # Then turn in to the centre.
    lead = catmull_rom([pts[-60], pts[-1], (cx, cy)], 60)
    lead = lead[lead.index(pts[-1]) if pts[-1] in lead else 0:]
    return pts[:-1] + lead[1:]


def _layout(theme: ThemeInfo, rng: random.Random) -> tuple[list[Point], list[Point], list[float]]:
    """Pick a path and place the spaces along it, retrying until no two
    spaces overlap (the randomness is gentle, so this nearly always works
    first time)."""
    r = theme.tile_radius
    for attempt in range(60):
        path = _spiral_path(rng, r) if theme.shape == "spiral" else _rows_path(rng, r)
        length = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
        spacing = 2 * r * rng.uniform(1.22, 1.32)
        n = max(12, int(length // spacing) + 1)
        radii = [r] * n
        radii[0] = r * 1.15
        radii[-1] = r * (1.4 if theme.shape == "spiral" else 1.3)
        # Give the bigger FINISH space its extra room: spread the other
        # spaces over the path minus that extra, then put FINISH at the end.
        extra = radii[-1] - r + (r * 0.45 if theme.shape == "spiral" else 6)
        positions = points_along(_trim_end(path, extra), n)[:-1] + [path[-1]]
        if _spaces_fit(positions, radii):
            return path, positions, radii
    # Extremely unlikely fallback: fewer, more widely spaced stones.
    positions = points_along(path, max(12, n - 6))
    radii = [r] * len(positions)
    radii[0] = r * 1.15
    radii[-1] = r * 1.3
    return path, positions, radii


def _trim_end(points: list[Point], amount: float) -> list[Point]:
    """The polyline with `amount` px of length cut off its end."""
    remaining = amount
    pts = list(points)
    while len(pts) > 2 and remaining > 0:
        seg = math.dist(pts[-2], pts[-1])
        if seg > remaining:
            t = (seg - remaining) / seg
            a, b = pts[-2], pts[-1]
            pts[-1] = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            break
        remaining -= seg
        pts.pop()
    return pts


def _spaces_fit(positions: list[Point], radii: list[float]) -> bool:
    x0, y0, x1, y1 = BOARD_BOX
    for (x, y), rad in zip(positions, radii):
        if x - rad < x0 - 5 or x + rad > x1 + 5 or y - rad < y0 - 5 or y + rad > y1 + 5:
            return False
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            need = (radii[i] + radii[j]) * (1.04 if j == i + 1 else 1.12)
            if math.dist(positions[i], positions[j]) < need:
                return False
    return True


def _choose_special_indices(rng: random.Random, n: int) -> tuple[list[int], list[int]]:
    """Bonus and hazard spaces: never right next to START/FINISH and at
    least 3 apart, so 'forward 2'/'back 2' always lands on a word space."""
    candidates = list(range(3, n - 3))
    rng.shuffle(candidates)
    want = max(2, round((n - 2) * 0.17))
    chosen: list[int] = []
    for idx in candidates:
        if all(abs(idx - c) >= 3 for c in chosen):
            chosen.append(idx)
        if len(chosen) >= want:
            break
    chosen.sort()
    # Alternate bonus/hazard along the path (random which comes first) so
    # they're spread out rather than all the good ones bunched together.
    first_bonus = rng.random() < 0.5
    bonus = [c for i, c in enumerate(chosen) if (i % 2 == 0) == first_bonus]
    hazard = [c for c in chosen if c not in bonus]
    return bonus, hazard


def build_adventure_board(child_name: str, words: list[str], theme: str = "treasure", seed: int | None = None) -> AdventureBoard:
    """Lay out a fresh random board for `theme` ('random' picks one)."""
    clean_words = [w.strip() for w in words if w.strip()]
    if not clean_words:
        raise ValueError("At least one word is required")
    if seed is None:
        seed = random.randrange(1, 10**9)
    if theme == "random":
        theme = random.Random(seed).choice(THEME_CHOICES)
    if theme not in THEMES:
        raise ValueError(f"Unknown theme {theme!r} - choose from {', '.join(THEME_CHOICES)}")
    info = THEMES[theme]
    # Mix the theme into the seed so two themes never share a path shape.
    rng = random.Random(f"{seed}-{theme}")

    path, positions, radii = _layout(info, rng)
    n = len(positions)
    bonus, hazard = _choose_special_indices(rng, n)
    word_slots = [i for i in range(1, n - 1) if i not in bonus and i not in hazard]
    word_seq = generate_word_grid(clean_words, rows=1, cols=len(word_slots), rng=rng)[0]
    # generate_word_grid only avoids repeats in adjacent cells of its own
    # row; specials break the run, so also avoid the same word either
    # side of a special by a light shuffle pass.
    spaces = [Space(WORD) for _ in range(n)]
    spaces[0] = Space(START)
    spaces[-1] = Space(FINISH)
    for i in bonus:
        spaces[i] = Space(BONUS)
    for i in hazard:
        spaces[i] = Space(HAZARD)
    for slot, word in zip(word_slots, word_seq):
        spaces[slot] = Space(WORD, word)

    return AdventureBoard(
        theme=theme, child_name=child_name, words=clean_words, seed=seed,
        spaces=spaces, positions=positions, radii=radii, path=path,
    )


# ---------------------------------------------------------------------------
# Little theme pictures
# ---------------------------------------------------------------------------

GOLD = (255, 205, 60)
SAND = (250, 231, 178)
SEA = (205, 236, 250)
GRASS = (222, 242, 205)
POND = (186, 224, 245)


def icon_coin(c: Canvas, cx: float, cy: float, s: float) -> None:
    c.circle(cx, cy, s * 0.48, fill=GOLD, outline=darker(GOLD, 0.6), width=3)
    c.circle(cx, cy, s * 0.36, outline=darker(GOLD, 0.75), width=2)
    draw_star(c, cx, cy, s * 0.26, fill=lighter(GOLD, 0.5), outline=darker(GOLD, 0.6), width=2)


def icon_crab(c: Canvas, cx: float, cy: float, s: float) -> None:
    red = (240, 95, 80)
    dark = darker(red, 0.6)
    for d in (-1, 1):
        for k in range(3):
            y = cy + s * (0.02 + k * 0.1)
            c.line([(cx + d * s * 0.25, y), (cx + d * s * 0.47, y + s * 0.1)], fill=dark, width=s * 0.05)
        c.line([(cx + d * s * 0.2, cy - s * 0.05), (cx + d * s * 0.36, cy - s * 0.25)], fill=dark, width=s * 0.06)
        c.circle(cx + d * s * 0.38, cy - s * 0.3, s * 0.13, fill=red, outline=dark, width=2)
        c.polygon([(cx + d * s * 0.38, cy - s * 0.3), (cx + d * s * 0.5, cy - s * 0.46), (cx + d * s * 0.3, cy - s * 0.45)], fill=WHITE)
        c.line([(cx + d * s * 0.09, cy - s * 0.08), (cx + d * s * 0.11, cy - s * 0.24)], fill=dark, width=s * 0.04)
        c.circle(cx + d * s * 0.11, cy - s * 0.26, s * 0.07, fill=WHITE, outline=dark, width=2)
        c.circle(cx + d * s * 0.11, cy - s * 0.25, s * 0.03, fill=INK)
    c.ellipse(cx, cy + s * 0.08, s * 0.3, s * 0.2, fill=red, outline=dark, width=3)


def icon_rocket(c: Canvas, cx: float, cy: float, s: float) -> None:
    red = (240, 90, 90)
    c.polygon([(cx - s * 0.1, cy + s * 0.3), (cx, cy + s * 0.52), (cx + s * 0.1, cy + s * 0.3)], fill=(255, 170, 50))
    c.polygon([(cx - s * 0.05, cy + s * 0.3), (cx, cy + s * 0.42), (cx + s * 0.05, cy + s * 0.3)], fill=(255, 230, 90))
    for d in (-1, 1):
        c.polygon([(cx + d * s * 0.12, cy + s * 0.05), (cx + d * s * 0.27, cy + s * 0.3), (cx + d * s * 0.12, cy + s * 0.28)],
                  fill=red, outline=darker(red), width=2)
    c.ellipse(cx, cy, s * 0.14, s * 0.34, fill=(235, 238, 248), outline=INK, width=3)
    c.polygon([(cx - s * 0.12, cy - s * 0.18), (cx, cy - s * 0.48), (cx + s * 0.12, cy - s * 0.18)], fill=red, outline=darker(red), width=2)
    c.circle(cx, cy - s * 0.02, s * 0.07, fill=(120, 200, 245), outline=INK, width=2)


def icon_black_hole(c: Canvas, cx: float, cy: float, s: float) -> None:
    colors = [(200, 180, 245), (160, 125, 230), (110, 75, 190), (60, 35, 110)]
    for i, col in enumerate(colors):
        c.circle(cx, cy, s * (0.48 - i * 0.1), fill=col)
    pts = []
    for i in range(80):
        t = i / 79
        a = t * 3.2 * math.pi
        rr = s * 0.46 * (1 - t)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    c.line(pts, fill=WHITE, width=s * 0.04)
    c.circle(cx, cy, s * 0.1, fill=(25, 15, 45))


def icon_rainbow(c: Canvas, cx: float, cy: float, s: float) -> None:
    band = s * 0.075
    for i, col in enumerate(RAINBOW[:6]):
        rr = s * 0.44 - i * band
        pts = [(cx + rr * math.cos(math.radians(a)), cy + s * 0.15 - rr * math.sin(math.radians(a))) for a in range(0, 181, 6)]
        c.line(pts, fill=col, width=band + 1, round_caps=False)
    draw_cloud(c, cx - s * 0.37, cy + s * 0.2, s * 0.22)
    draw_cloud(c, cx + s * 0.37, cy + s * 0.2, s * 0.22)


def icon_rain_cloud(c: Canvas, cx: float, cy: float, s: float) -> None:
    for i, dx in enumerate((-0.22, 0, 0.22)):
        x, y = cx + dx * s, cy + s * (0.22 + 0.06 * (i % 2))
        c.polygon([(x, y - s * 0.1), (x - s * 0.06, y + s * 0.02), (x, y + s * 0.09), (x + s * 0.06, y + s * 0.02)], fill=(80, 160, 235))
        c.circle(x, y + s * 0.03, s * 0.06, fill=(80, 160, 235))
    draw_cloud(c, cx, cy - s * 0.1, s * 0.42, fill=(200, 205, 220), outline=(120, 125, 145))


def icon_dragonfly(c: Canvas, cx: float, cy: float, s: float) -> None:
    wing = (190, 230, 250)
    for d in (-1, 1):
        c.ellipse(cx + d * s * 0.22, cy - s * 0.12, s * 0.22, s * 0.09, fill=wing, outline=(90, 150, 200), width=2)
        c.ellipse(cx + d * s * 0.2, cy + s * 0.04, s * 0.19, s * 0.08, fill=wing, outline=(90, 150, 200), width=2)
    c.line([(cx, cy - s * 0.18), (cx, cy + s * 0.45)], fill=(60, 140, 200), width=s * 0.08)
    c.circle(cx, cy - s * 0.24, s * 0.09, fill=(60, 140, 200), outline=INK, width=2)
    for d in (-1, 1):
        c.circle(cx + d * s * 0.05, cy - s * 0.27, s * 0.035, fill=INK)


def icon_splash(c: Canvas, cx: float, cy: float, s: float) -> None:
    blue = (70, 150, 230)
    for k, (rx, ry) in enumerate(((0.46, 0.13), (0.3, 0.08))):
        c.ellipse(cx, cy + s * 0.3, s * rx, s * ry, fill=lighter(blue, 0.7) if k == 0 else None, outline=blue, width=3)
    # Drops flying up and out of the water.
    for dx, dy, rr in ((-0.3, -0.05, 0.08), (0.0, -0.25, 0.1), (0.3, -0.05, 0.08)):
        x, y = cx + dx * s, cy + dy * s
        r = rr * s
        c.circle(x, y + r * 0.3, r, fill=blue)
        c.polygon([(x - r * 0.95, y + r * 0.1), (x, y - r * 1.9), (x + r * 0.95, y + r * 0.1)], fill=blue)
        c.circle(x - r * 0.3, y + r * 0.1, r * 0.25, fill=WHITE)
    for d in (-1, 1):
        c.line([(cx + d * s * 0.12, cy + s * 0.18), (cx + d * s * 0.2, cy + s * 0.05)], fill=blue, width=s * 0.04)


def draw_palm_islet(c: Canvas, cx: float, cy: float, s: float, rng: random.Random) -> None:
    c.ellipse(cx, cy + s * 0.42, s * 0.62, s * 0.2, fill=lighter(SEA, -0.0), outline=WHITE, width=4)
    c.ellipse(cx, cy + s * 0.42, s * 0.55, s * 0.16, fill=SAND, outline=darker(SAND, 0.8), width=2)
    lean = rng.choice([-1, 1])
    trunk = [(cx + lean * s * 0.05 * t ** 2 * 3, cy + s * 0.4 - s * 0.75 * t) for t in [i / 10 for i in range(11)]]
    c.line(trunk, fill=(160, 110, 60), width=s * 0.09)
    for p in trunk[1::2]:
        c.line([(p[0] - s * 0.045, p[1]), (p[0] + s * 0.045, p[1])], fill=(120, 80, 40), width=2)
    top = trunk[-1]
    for ang in (-160, -120, -60, -20, 200 if lean > 0 else -200):
        a = math.radians(ang)
        tip = (top[0] + math.cos(a) * s * 0.45, top[1] + math.sin(a) * s * 0.3 + s * 0.12)
        mid = ((top[0] + tip[0]) / 2, (top[1] + tip[1]) / 2 - s * 0.1)
        leaf = catmull_rom([top, mid, tip], 10)
        c.line(leaf, fill=(70, 165, 80), width=s * 0.1)
    for d in (-1, 1):
        c.circle(top[0] + d * s * 0.05, top[1] + s * 0.06, s * 0.05, fill=(140, 90, 50))


def draw_fish(c: Canvas, cx: float, cy: float, s: float, color, facing: int = 1) -> None:
    c.polygon([(cx - facing * s * 0.25, cy), (cx - facing * s * 0.48, cy - s * 0.18), (cx - facing * s * 0.48, cy + s * 0.18)],
              fill=color, outline=darker(color), width=2)
    c.ellipse(cx, cy, s * 0.32, s * 0.2, fill=color, outline=darker(color), width=2)
    c.circle(cx + facing * s * 0.17, cy - s * 0.04, s * 0.045, fill=INK)


def draw_wave(c: Canvas, cx: float, cy: float, s: float, color=(130, 195, 230)) -> None:
    pts = [(cx - s / 2 + s * t, cy + math.sin(t * 2 * math.pi * 1.5) * s * 0.08) for t in [i / 30 for i in range(31)]]
    c.line(pts, fill=color, width=max(4, s * 0.07))


def draw_ship(c: Canvas, cx: float, cy: float, s: float) -> None:
    c.line([(cx, cy + s * 0.1), (cx, cy - s * 0.5)], fill=(120, 80, 40), width=s * 0.05)
    c.polygon([(cx + s * 0.03, cy - s * 0.47), (cx + s * 0.36, cy + s * 0.02), (cx + s * 0.03, cy + s * 0.02)], fill=WHITE, outline=INK, width=3)
    c.polygon([(cx - s * 0.03, cy - s * 0.4), (cx - s * 0.3, cy + s * 0.02), (cx - s * 0.03, cy + s * 0.02)], fill=(255, 235, 200), outline=INK, width=3)
    c.polygon([(cx, cy - s * 0.5), (cx + s * 0.16, cy - s * 0.45), (cx, cy - s * 0.4)], fill=(240, 90, 90))
    c.polygon([(cx - s * 0.48, cy + s * 0.08), (cx + s * 0.48, cy + s * 0.08), (cx + s * 0.34, cy + s * 0.3), (cx - s * 0.34, cy + s * 0.3)],
              fill=(170, 110, 60), outline=INK, width=3)
    draw_wave(c, cx, cy + s * 0.36, s * 0.9)


def draw_chest(c: Canvas, cx: float, cy: float, s: float) -> None:
    brown = (175, 110, 55)
    for i, dx in enumerate((-0.32, -0.12, 0.1, 0.3)):
        c.circle(cx + dx * s, cy - s * 0.24 - (i % 2) * s * 0.05, s * 0.09, fill=GOLD, outline=darker(GOLD, 0.6), width=2)
    c.rect(cx - s * 0.42, cy - s * 0.38, cx + s * 0.42, cy - s * 0.12, fill=darker(brown, 0.85), outline=INK, width=3, radius=s * 0.12)
    c.rect(cx - s * 0.42, cy - s * 0.15, cx + s * 0.42, cy + s * 0.25, fill=brown, outline=INK, width=3, radius=s * 0.04)
    for dx in (-0.3, 0.3):
        c.rect(cx + dx * s - s * 0.04, cy - s * 0.38, cx + dx * s + s * 0.04, cy + s * 0.25, fill=GOLD, outline=darker(GOLD, 0.6), width=2)
    c.rect(cx - s * 0.07, cy - s * 0.18, cx + s * 0.07, cy - s * 0.02, fill=GOLD, outline=INK, width=2, radius=3)


def draw_moon(c: Canvas, cx: float, cy: float, r: float) -> None:
    moon = (250, 240, 190)
    c.circle(cx, cy, r, fill=moon, outline=darker(moon, 0.6), width=5)
    for dx, dy, rr in ((-0.5, -0.45, 0.16), (0.55, -0.35, 0.12), (-0.55, 0.45, 0.13), (0.45, 0.5, 0.17), (0.0, -0.72, 0.09)):
        c.circle(cx + dx * r, cy + dy * r, rr * r, fill=darker(moon, 0.9), outline=darker(moon, 0.75), width=2)


def draw_planet(c: Canvas, cx: float, cy: float, r: float, color, ring: bool) -> None:
    if ring:
        c.ellipse(cx, cy, r * 1.75, r * 0.5, outline=darker(color, 0.7), width=max(4, r * 0.12))
    c.circle(cx, cy, r, fill=color, outline=darker(color, 0.55), width=3)
    c.circle(cx - r * 0.35, cy - r * 0.35, r * 0.22, fill=lighter(color, 0.55))
    if ring:
        pts = [(cx + r * 1.75 * math.cos(math.radians(a)), cy + r * 0.5 * math.sin(math.radians(a))) for a in range(5, 176, 5)]
        c.line(pts, fill=darker(color, 0.7), width=max(4, r * 0.12))


def draw_frog(c: Canvas, cx: float, cy: float, s: float) -> None:
    green = (110, 200, 90)
    dark = darker(green, 0.55)
    for d in (-1, 1):
        c.ellipse(cx + d * s * 0.33, cy + s * 0.28, s * 0.2, s * 0.1, fill=green, outline=dark, width=3)
    c.ellipse(cx, cy + s * 0.08, s * 0.42, s * 0.3, fill=green, outline=dark, width=3)
    c.ellipse(cx, cy + s * 0.16, s * 0.26, s * 0.17, fill=lighter(green, 0.55))
    for d in (-1, 1):
        c.circle(cx + d * s * 0.2, cy - s * 0.2, s * 0.14, fill=green, outline=dark, width=3)
        c.circle(cx + d * s * 0.2, cy - s * 0.2, s * 0.085, fill=WHITE)
        c.circle(cx + d * s * 0.21, cy - s * 0.19, s * 0.045, fill=INK)
    smile = [(cx + s * 0.18 * math.cos(math.radians(a)), cy + s * 0.0 + s * 0.08 * math.sin(math.radians(a))) for a in range(15, 166, 10)]
    c.line(smile, fill=dark, width=s * 0.035)
    for d in (-1, 1):
        c.circle(cx + d * s * 0.27, cy + s * 0.05, s * 0.05, fill=(255, 160, 170))


def draw_snail(c: Canvas, cx: float, cy: float, s: float) -> None:
    body = (255, 200, 120)
    shell = (250, 130, 170)
    c.polygon([(cx - s * 0.5, cy + s * 0.3), (cx + s * 0.45, cy + s * 0.3), (cx + s * 0.5, cy + s * 0.05), (cx + s * 0.35, cy - s * 0.05),
               (cx + s * 0.25, cy + s * 0.15), (cx - s * 0.45, cy + s * 0.18)], fill=body, outline=darker(body), width=3)
    for d in (0.36, 0.46):
        c.line([(cx + s * d - s * 0.02, cy - s * 0.0), (cx + s * d + s * 0.02, cy - s * 0.25)], fill=darker(body), width=s * 0.03)
        c.circle(cx + s * d + s * 0.02, cy - s * 0.27, s * 0.04, fill=INK)
    c.circle(cx - s * 0.08, cy - s * 0.02, s * 0.3, fill=shell, outline=darker(shell, 0.6), width=3)
    pts = []
    for i in range(70):
        t = i / 69
        a = t * 4.5 * math.pi
        rr = s * 0.27 * (1 - t)
        pts.append((cx - s * 0.08 + rr * math.cos(a), cy - s * 0.02 + rr * math.sin(a)))
    c.line(pts, fill=darker(shell, 0.6), width=s * 0.035)


def draw_reeds(c: Canvas, cx: float, cy: float, s: float, rng: random.Random) -> None:
    for i in range(3):
        dx = (i - 1) * s * 0.18
        h = s * rng.uniform(0.75, 1.0)
        bend = rng.uniform(-0.12, 0.12) * s
        stem = catmull_rom([(cx + dx, cy + s * 0.4), (cx + dx + bend * 0.4, cy + s * 0.4 - h * 0.5), (cx + dx + bend, cy + s * 0.4 - h)], 10)
        c.line(stem, fill=(90, 160, 70), width=s * 0.05)
        top = stem[-1]
        c.ellipse(top[0], top[1] + s * 0.12, s * 0.06, s * 0.13, fill=(140, 90, 55), outline=darker((140, 90, 55)), width=2)
    for d in (-1, 1):
        leaf = catmull_rom([(cx, cy + s * 0.4), (cx + d * s * 0.2, cy + s * 0.05), (cx + d * s * 0.35, cy - s * 0.05)], 10)
        c.line(leaf, fill=(110, 185, 85), width=s * 0.06)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

@dataclass
class _Style:
    background: tuple
    title_colors: list
    chip_colors: list
    tile_colors: list
    tile_outline: Callable | None
    path_color: tuple
    bonus_icon: Callable
    hazard_icon: Callable
    bonus_fill: tuple
    hazard_fill: tuple
    legend_fill: tuple


STYLES: dict[str, _Style] = {
    "treasure": _Style(
        SEA, RAINBOW, PASTEL_RAINBOW,
        [(255, 190, 170), (175, 228, 215), (255, 225, 150), (205, 230, 160), (200, 210, 250)],
        None, (200, 70, 60), icon_coin, icon_crab, (255, 236, 160), (255, 205, 200), (255, 250, 235),
    ),
    "space": _Style(
        (236, 236, 255), [(255, 212, 59), (255, 150, 90), (120, 205, 245), (190, 150, 255), (255, 120, 190)],
        [(220, 215, 255), (200, 235, 255), (255, 220, 240), (255, 240, 190), (210, 245, 220)],
        [(255, 200, 160), (180, 220, 255), (220, 200, 255), (200, 240, 190), (255, 210, 225), (255, 235, 160)],
        None, (160, 150, 230), icon_rocket, icon_black_hole, (255, 236, 200), (225, 215, 250), (250, 250, 255),
    ),
    "rainbow": _Style(
        (245, 251, 255), RAINBOW, PASTEL_RAINBOW, PASTEL_RAINBOW,
        None, (225, 228, 238), icon_rainbow, icon_rain_cloud, (255, 255, 255), (232, 236, 245), (255, 255, 255),
    ),
    "pond": _Style(
        GRASS, [(120, 205, 90), (70, 185, 230), (255, 212, 59), (255, 120, 190), (150, 120, 230)],
        [(205, 238, 186), (186, 226, 247), (255, 240, 170), (255, 205, 230)],
        [(196, 234, 160), (175, 222, 150), (210, 240, 175)],
        None, (110, 160, 220), icon_dragonfly, icon_splash, (225, 245, 255), (210, 230, 250), (250, 255, 245),
    ),
}


def _avoid_list(board: AdventureBoard, pad: float) -> list[tuple[Point, float]]:
    avoid = [(p, r + pad) for p, r in zip(board.positions, board.radii)]
    for p in resample_polyline(board.path, 40):
        avoid.append((p, pad))
    return avoid


def _draw_background(c: Canvas, board: AdventureBoard, rng: random.Random) -> None:
    style = STYLES[board.theme]
    x0, y0, x1, y1 = BOARD_BOX
    r = board.info.tile_radius

    if board.theme == "treasure":
        # A sandy island that hugs the path, with a white surf edge.
        island = resample_polyline(board.path, 30)
        bumps = [rng.uniform(0, 2 * math.pi) for _ in range(3)]

        def rad(i: int, extra: float) -> float:
            t = i / max(1, len(island) - 1)
            return r * (1.55 + 0.25 * math.sin(t * 19 + bumps[0]) + 0.15 * math.sin(t * 7 + bumps[1])) + extra

        for i, p in enumerate(island):
            c.circle(p[0], p[1], rad(i, 22), fill=(170, 220, 240))
        for i, p in enumerate(island):
            c.circle(p[0], p[1], rad(i, 10), fill=WHITE)
        for i, p in enumerate(island):
            c.circle(p[0], p[1], rad(i, 0), fill=SAND)
        # Specks in the sand.
        for p in island[::3]:
            a = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(r * 1.05, r * 1.4)
            c.circle(p[0] + math.cos(a) * d, p[1] + math.sin(a) * d, rng.uniform(3, 6), fill=darker(SAND, 0.85))

    elif board.theme == "pond":
        water = resample_polyline(board.path, 30)
        phase = rng.uniform(0, 6.28)
        for extra, col in ((14, (150, 200, 120)), (0, POND)):
            for i, p in enumerate(water):
                t = i / max(1, len(water) - 1)
                c.circle(p[0], p[1], r * (1.6 + 0.2 * math.sin(t * 15 + phase)) + extra, fill=col)
        # Ripples on the water, between pads.
        for p in water[5::9]:
            if all(math.dist(p, q) > rr + 30 for q, rr in zip(board.positions, board.radii)):
                c.ellipse(p[0], p[1], 26, 9, outline=(140, 195, 235), width=3)

    elif board.theme == "space":
        for _ in range(140):
            x, y = rng.uniform(0, c.width), rng.uniform(250, 1940)
            c.circle(x, y, rng.uniform(1.5, 3.5), fill=(190, 185, 235))

    elif board.theme == "rainbow":
        # A soft grey 'road' under the spiral, with a dashed centre line.
        c.arc_band(board.path, fill=(225, 230, 242), width=r * 2.35)
        c.dashed_line(board.path, fill=WHITE, width=8, dash=30, gap=26)


def _draw_path(c: Canvas, board: AdventureBoard) -> None:
    style = STYLES[board.theme]
    if board.theme == "treasure":
        c.dashed_line(board.path, fill=style.path_color, width=9, dash=34, gap=22)
    elif board.theme == "space":
        c.dotted_line(board.path, fill=style.path_color, radius=7, spacing=26)
    elif board.theme == "pond":
        # Little hop arcs between pads instead of a continuous line.
        for (a, ra), (b, rb) in zip(zip(board.positions, board.radii), zip(board.positions[1:], board.radii[1:])):
            d = math.dist(a, b)
            if d <= ra + rb:
                continue
            ux, uy = (b[0] - a[0]) / d, (b[1] - a[1]) / d
            s = (a[0] + ux * (ra + 4), a[1] + uy * (ra + 4))
            e = (b[0] - ux * (rb + 4), b[1] - uy * (rb + 4))
            gap = math.dist(s, e)
            mid = ((s[0] + e[0]) / 2 + uy * gap * 0.35, (s[1] + e[1]) / 2 - ux * gap * 0.35)
            if mid[1] > (s[1] + e[1]) / 2:  # always arc 'upwards' on the page
                mid = ((s[0] + e[0]) / 2 - uy * gap * 0.35, (s[1] + e[1]) / 2 + ux * gap * 0.35)
            c.dotted_line(catmull_rom([s, mid, e], 16), fill=style.path_color, radius=5, spacing=17)


def _direction_arrows(c: Canvas, board: AdventureBoard, color) -> None:
    """Small chevrons in the gaps between spaces so it's obvious which
    way to go - more of them near the start, where it matters most."""
    pts, radii = board.positions, board.radii
    for i in list(range(0, 3)) + list(range(5, len(pts) - 1, 5)):
        if i + 1 >= len(pts):
            continue
        a, b = pts[i], pts[i + 1]
        d = math.dist(a, b)
        gap = d - radii[i] - radii[i + 1]
        if gap < 26:
            continue
        ux, uy = (b[0] - a[0]) / d, (b[1] - a[1]) / d
        t = radii[i] + gap / 2
        cx, cy = a[0] + ux * t, a[1] + uy * t
        sz = min(18, gap * 0.35)
        px, py = -uy, ux
        tip = (cx + ux * sz, cy + uy * sz)
        c.polygon([tip, (cx - ux * sz + px * sz, cy - uy * sz + py * sz), (cx - ux * sz * 0.3, cy - uy * sz * 0.3),
                   (cx - ux * sz - px * sz, cy - uy * sz - py * sz)], fill=color, outline=WHITE, width=2)


def _draw_space(c: Canvas, board: AdventureBoard, i: int, rng: random.Random) -> None:
    style = STYLES[board.theme]
    info = board.info
    space = board.spaces[i]
    x, y = board.positions[i]
    r = board.radii[i]

    if space.kind == START:
        fill = (130, 215, 120)
        c.circle(x, y + 6, r, fill=darker(fill, 0.75))
        c.circle(x, y, r, fill=fill, outline=INK, width=5)
        c.circle(x, y, r * 0.84, outline=WHITE, width=4)
        c.word(x, y, "START", r * 0.48, r * 1.55, fill=WHITE, halo=darker(fill, 0.5))
        return
    if space.kind == FINISH:
        if board.theme == "space":
            draw_moon(c, x, y, r)
            c.word(x, y, "FINISH", r * 0.42, r * 1.55, fill=INK, halo=WHITE)
            return
        if board.theme == "rainbow":
            c.polygon(star_points(x, y + 8, r * 1.15, r * 0.62), fill=darker(GOLD, 0.75))
            c.polygon(star_points(x, y, r * 1.15, r * 0.62), fill=GOLD, outline=INK, width=5)
            c.word(x, y + r * 0.06, "FINISH", r * 0.36, r * 1.05, fill=INK, halo=WHITE)
            return
        fill = GOLD if board.theme == "treasure" else (255, 190, 215)
        c.circle(x, y + 6, r, fill=darker(fill, 0.75))
        c.circle(x, y, r, fill=fill, outline=INK, width=5)
        if board.theme == "treasure":
            # The X that marks the spot.
            for d in (-1, 1):
                c.line([(x - r * 0.55, y - d * r * 0.55), (x + r * 0.55, y + d * r * 0.55)], fill=(220, 80, 60), width=r * 0.16)
        else:
            for k in range(8):
                a = math.radians(k * 45 + 22)
                c.ellipse(x + math.cos(a) * r * 0.55, y + math.sin(a) * r * 0.55, r * 0.3, r * 0.3, fill=WHITE, outline=(240, 130, 180), width=2)
        c.word(x, y, "FINISH", r * 0.42, r * 1.55, fill=INK, halo=WHITE)
        return

    # Ordinary and special spaces share a base shape per theme.
    if space.kind == BONUS:
        fill = style.bonus_fill
    elif space.kind == HAZARD:
        fill = style.hazard_fill
    else:
        fill = style.tile_colors[i % len(style.tile_colors)]

    if board.theme == "space" and space.kind == WORD:
        draw_planet(c, x, y, r, fill, ring=rng.random() < 0.28)
    elif board.theme == "pond":
        pad = fill if space.kind == WORD else (196, 234, 160)
        notch = rng.uniform(0, 360)
        c.draw.pieslice([c.s(x - r), c.s(y - r + 5), c.s(x + r), c.s(y + r + 5)], notch + 24, notch - 24, fill=darker(pad, 0.7))
        c.draw.pieslice([c.s(x - r), c.s(y - r), c.s(x + r), c.s(y + r)], notch + 24, notch - 24, fill=pad,
                        outline=(70, 140, 60), width=c.w(4))
        for k in range(5):
            a = math.radians(notch + 180 + (k - 2) * 28)
            c.line([(x + math.cos(a) * r * 0.45, y + math.sin(a) * r * 0.45), (x + math.cos(a) * r * 0.85, y + math.sin(a) * r * 0.85)],
                   fill=darker(pad, 0.85), width=3)
        if space.kind != WORD:
            c.circle(x, y, r * 0.7, fill=fill, outline=(110, 160, 220), width=3)
    else:
        c.circle(x, y + 6, r, fill=darker(fill, 0.72))
        c.circle(x, y, r, fill=fill, outline=darker(fill, 0.45), width=4)
        # A little shine so they look like shiny pebbles / sweets.
        pts = [(x + r * 0.72 * math.cos(math.radians(a)), y + r * 0.72 * math.sin(math.radians(a))) for a in range(200, 251, 5)]
        c.line(pts, fill=WHITE, width=r * 0.09)

    if space.kind == WORD:
        c.word(x, y, space.word, r * 0.52, r * 1.62, fill=INK, halo=WHITE if board.theme != "rainbow" else None)
    else:
        icon = style.bonus_icon if space.kind == BONUS else style.hazard_icon
        label = info.bonus_label if space.kind == BONUS else info.hazard_label
        icon(c, x, y - r * 0.2, r * 1.0)
        font = c.fit_word_font(label, r * 0.3, r * 1.45)
        c.text_center(x, y + r * 0.58, label, font, fill=INK, stroke=3, stroke_fill=WHITE)


def _draw_decorations(c: Canvas, board: AdventureBoard, rng: random.Random) -> None:
    box = BOARD_BOX
    start, finish = board.positions[0], board.positions[-1]
    r0, rf = board.radii[0], board.radii[-1]
    theme = board.theme

    # A character / picture beside START (and FINISH), placed in whichever
    # nearby spot has the most room.
    def beside(p: Point, pr: float, size: float, avoid) -> Point | None:
        best, best_clear = None, -1.0
        for k in range(16):
            a = 2 * math.pi * k / 16
            q = (p[0] + math.cos(a) * (pr + size * 0.62), p[1] + math.sin(a) * (pr + size * 0.62))
            if not (box[0] + size / 2 < q[0] < box[2] - size / 2 and box[1] + size / 2 < q[1] < box[3] - size / 2):
                continue
            clear = min((math.dist(q, o) - orad for o, orad in avoid if math.dist(o, p) > 1), default=999)
            if clear > best_clear:
                best, best_clear = q, clear
        return best if best_clear > size * 0.3 else None

    avoid = _avoid_list(board, 12)
    start_pic = {"treasure": draw_ship, "space": icon_rocket, "rainbow": draw_snail, "pond": draw_frog}[theme]
    size = 170
    q = beside(start, r0, size, avoid)
    if q:
        start_pic(c, q[0], q[1], size)
        avoid.append((q, size * 0.55))
    if theme == "treasure":
        q = beside(finish, rf, 150, avoid)
        if q:
            draw_chest(c, q[0], q[1], 150)
            avoid.append((q, 80))

    if theme == "treasure":
        # Keep sea creatures off the island.
        island_avoid = avoid + [(p, board.info.tile_radius * 1.95) for p in resample_polyline(board.path, 35)]
        for p in scatter(rng, box, 3, 95, island_avoid):
            draw_palm_islet(c, p[0], p[1], 150, rng)
            island_avoid.append((p, 95))
        for p in scatter(rng, box, 4, 45, island_avoid):
            draw_fish(c, p[0], p[1], 85, rng.choice(RAINBOW), rng.choice([-1, 1]))
            island_avoid.append((p, 45))
        for p in scatter(rng, (0, 260, c.width, 1950), 14, 40, island_avoid):
            draw_wave(c, p[0], p[1], 70)
    elif theme == "space":
        for p in scatter(rng, box, 4, 55, avoid):
            draw_planet(c, p[0], p[1], rng.uniform(22, 34), rng.choice(PASTEL_RAINBOW), ring=rng.random() < 0.5)
            avoid.append((p, 60))
        for p in scatter(rng, (0, 260, c.width, 1950), 18, 24, avoid):
            draw_star(c, p[0], p[1], rng.uniform(12, 22), fill=(255, 220, 90), outline=(200, 160, 40), width=2,
                      rotation=rng.uniform(-110, -70))
    elif theme == "rainbow":
        for p in scatter(rng, box, 4, 80, avoid):
            draw_cloud(c, p[0], p[1], rng.uniform(80, 110))
            avoid.append((p, 85))
        for p in scatter(rng, box, 8, 36, avoid):
            draw_flower(c, p[0], p[1] - 20, 18, rng.choice(RAINBOW))
            avoid.append((p, 40))
        for p in scatter(rng, box, 10, 18, avoid):
            draw_star(c, p[0], p[1], 14, fill=GOLD, outline=darker(GOLD), width=2)
    elif theme == "pond":
        water_avoid = avoid + [(p, board.info.tile_radius * 1.85) for p in resample_polyline(board.path, 35)]
        for p in scatter(rng, box, 6, 55, water_avoid):
            draw_reeds(c, p[0], p[1], 110, rng)
            water_avoid.append((p, 60))
        for p in scatter(rng, box, 9, 32, water_avoid):
            draw_flower(c, p[0], p[1] - 16, 15, rng.choice(RAINBOW))
            water_avoid.append((p, 34))


def _draw_footer(c: Canvas, board: AdventureBoard) -> None:
    style = STYLES[board.theme]
    info = board.info
    # Chips sit on a light strip so they read cleanly even where the
    # island/pond spills down to them.
    draw_word_chips(c, CHIPS_Y, board.words, colors=style.chip_colors, max_width=c.width - 260,
                    backing=lighter(style.legend_fill, 0.3), backing_outline=darker(style.background, 0.8))

    x0, x1 = 70, c.width - 70
    c.rect(x0, LEGEND_TOP + 6, x1, LEGEND_BOTTOM + 6, fill=darker(style.legend_fill, 0.8), radius=28)
    c.rect(x0, LEGEND_TOP, x1, LEGEND_BOTTOM, fill=style.legend_fill, outline=INK, width=4, radius=28)
    c.text_center(c.width / 2, LEGEND_TOP + 40, "How to play", c.font(36), fill=INK)
    body = c.font(27, bold=False)
    top = LEGEND_TOP + 112
    step = 78
    col2 = c.width / 2 + 20
    draw_legend_row(c, x0 + 30, top, lambda cc, cx, cy, s: draw_dice(cc, cx, cy, s * 0.85, 5),
                    "Roll the die and move along.", body, icon_size=54)
    draw_legend_row(c, x0 + 30, top + step, lambda cc, cx, cy, s: draw_star(cc, cx, cy, s * 0.5),
                    "Read each word you land on!", body, icon_size=54)
    draw_legend_row(c, col2, top, style.bonus_icon, info.bonus_rule, body, icon_size=54)
    draw_legend_row(c, col2, top + step, style.hazard_icon, info.hazard_rule, body, icon_size=54)
    c.text_center(c.width / 2, LEGEND_BOTTOM - 34, "First one to the FINISH wins!", c.font(28), fill=MUTED)


def render_adventure_image(board: AdventureBoard) -> Image.Image:
    style = STYLES[board.theme]
    rng = random.Random(board.seed * 7 + 3)
    c = Canvas(background=style.background)

    # A soft coloured frame round the page.
    frame = darker(style.background, 0.88)
    c.rect(18, 18, c.width - 18, c.height - 18, outline=frame, width=14, radius=40)

    _draw_background(c, board, rng)
    _draw_path(c, board)
    _draw_decorations(c, board, rng)
    _direction_arrows(c, board, darker(style.path_color, 0.8) if board.theme != "rainbow" else (150, 150, 175))
    for i in range(len(board.positions)):
        _draw_space(c, board, i, rng)

    draw_fun_title(c, board.info.title, TITLE_Y, 96, colors=style.title_colors, rng=rng)
    draw_name_banner(c, BANNER_Y, board.child_name)
    _draw_footer(c, board)
    return c.finish()


def build_adventure_boards(child_name: str, words: list[str], theme: str = "mix", count: int = 1,
                           seed: int | None = None) -> list[AdventureBoard]:
    """`count` different boards. theme='mix' goes through all the themes
    (in a random order) before repeating any; 'random' picks each board's
    theme at random; otherwise every board uses that theme (each with its
    own random path)."""
    if count < 1:
        raise ValueError("At least one board is required")
    master = random.Random(seed)
    order = list(THEME_CHOICES)
    master.shuffle(order)
    boards = []
    for i in range(count):
        board_theme = order[i % len(order)] if theme == "mix" else theme
        boards.append(build_adventure_board(child_name, words, theme=board_theme, seed=master.randrange(1, 10**9)))
    return boards


def _as_list(boards) -> list[AdventureBoard]:
    return [boards] if isinstance(boards, AdventureBoard) else list(boards)


def export_adventure_pdf(boards: AdventureBoard | list[AdventureBoard], output_path: str) -> None:
    """One board per page (pass a single board or a list)."""
    boards = _as_list(boards)
    title = boards[0].info.title if len(boards) == 1 else "Adventure Boards"
    export_full_page_images_pdf([render_adventure_image(b) for b in boards], output_path, title=title, margin_mm=5)


def export_adventure_docx(boards: AdventureBoard | list[AdventureBoard], output_path: str) -> None:
    export_full_page_images_docx([render_adventure_image(b) for b in _as_list(boards)], output_path, margin_cm=0.5)
