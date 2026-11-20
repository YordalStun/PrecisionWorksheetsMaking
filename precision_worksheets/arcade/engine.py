"""A tiny 2D game engine on top of QPainter for the Word Arcade.

Every game is a `GameCanvas` subclass that draws itself each frame (about
60fps) into a fixed 1000 x 680 "design" space that is scaled to fill the
window - so games always fill the screen with no awkward blank areas,
whatever size the window is, and game code never has to think about
pixels or resizing.

The base class gives every game the same production polish for free:
  - an animated themed background (drifting clouds / bubbles / stars ...)
  - particle bursts, floating "+1" text, screen shake
  - a "Ready? 3, 2, 1, GO!" countdown before play starts
  - a heads-up bar with the game's title, score and timer
  - a results card with 1-3 stars, Play again / Back to the arcade
  - optional little synthesized sound effects (see sound.py)

Subclasses implement: start_game(), tick(dt), draw_game(p),
click(x, y) and optionally key(key).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QElapsedTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from . import sound

W, H = 1000.0, 680.0
FONT_FAMILY = "Comic Sans MS"
INK = QColor("#2d2840")
WHITE = QColor("#ffffff")
GOOD = QColor("#2ec97a")
BAD = QColor("#ff5d73")
GOLD = QColor("#ffcc33")
RAINBOW = ["#ff6363", "#ffa53c", "#ffd43b", "#78cd5a", "#46b9e6", "#9678e6", "#ff78be"]


def qc(c) -> QColor:
    return c if isinstance(c, QColor) else QColor(c)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out_back(t: float) -> float:
    t = max(0.0, min(1.0, t))
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

_family_checked = False


def _ensure_family() -> None:
    """Use Comic Sans MS (on every Windows PC); if it's missing, load the
    bundled Comic Neue lookalike so the games keep their friendly look."""
    global _family_checked, FONT_FAMILY
    if _family_checked:
        return
    _family_checked = True
    from PySide6.QtGui import QFontDatabase

    if "Comic Sans MS" in QFontDatabase.families():
        return
    import os

    folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
    for name in ("ComicNeue-Bold.otf", "ComicNeue-Regular.otf"):
        fid = QFontDatabase.addApplicationFont(os.path.join(folder, name))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            FONT_FAMILY = fams[0]


def font(size: float, bold: bool = True) -> QFont:
    _ensure_family()
    f = QFont(FONT_FAMILY)
    f.setPointSizeF(max(1.0, size))
    f.setBold(bold)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def fit_size(text: str, max_w: float, size: float, min_size: float = 8, bold: bool = True) -> float:
    while size > min_size:
        if QFontMetricsF(font(size, bold)).horizontalAdvance(text) <= max_w:
            return size
        size -= 1
    return min_size


def text(p: QPainter, s: str, cx: float, cy: float, size: float, color=INK, outline=None, outline_w: float = 0,
         bold: bool = True, max_w: float | None = None, align: str = "center") -> float:
    """Draw `s` centred on (cx, cy) (or left/right aligned at cx), with an
    optional thick outline - the 'game title' look. Shrinks to max_w.
    Returns the width drawn."""
    if max_w:
        size = fit_size(s, max_w, size, bold=bold)
    f = font(size, bold)
    fm = QFontMetricsF(f)
    tw = fm.horizontalAdvance(s)
    x = cx - tw / 2 if align == "center" else (cx if align == "left" else cx - tw)
    y = cy + (fm.ascent() - fm.descent()) / 2
    path = QPainterPath()
    path.addText(QPointF(x, y), f, s)
    if outline is not None and outline_w:
        p.setPen(QPen(qc(outline), outline_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(qc(color))
    p.drawPath(path)
    return tw


def rounded(p: QPainter, r: QRectF, radius: float, fill, outline=None, width: float = 0, shadow: float = 0) -> None:
    if shadow:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawRoundedRect(r.translated(0, shadow), radius, radius)
    p.setPen(QPen(qc(outline), width) if outline is not None and width else Qt.NoPen)
    p.setBrush(qc(fill) if not isinstance(fill, (QBrush, QLinearGradient, QRadialGradient)) else fill)
    p.drawRoundedRect(r, radius, radius)


def circle(p: QPainter, x: float, y: float, r: float, fill, outline=None, width: float = 0) -> None:
    p.setPen(QPen(qc(outline), width) if outline is not None and width else Qt.NoPen)
    p.setBrush(qc(fill) if not isinstance(fill, (QBrush, QLinearGradient, QRadialGradient)) else fill)
    p.drawEllipse(QPointF(x, y), r, r)


def ellipse(p: QPainter, x: float, y: float, rx: float, ry: float, fill, outline=None, width: float = 0) -> None:
    p.setPen(QPen(qc(outline), width) if outline is not None and width else Qt.NoPen)
    p.setBrush(qc(fill) if not isinstance(fill, (QBrush, QLinearGradient, QRadialGradient)) else fill)
    p.drawEllipse(QPointF(x, y), rx, ry)


def star_path(cx: float, cy: float, r: float, inner: float = 0.45, n: int = 5, rot: float = -90) -> QPainterPath:
    path = QPainterPath()
    for i in range(n * 2):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot + i * 180 / n)
        pt = QPointF(cx + rr * math.cos(a), cy + rr * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    return path


def star(p: QPainter, cx: float, cy: float, r: float, fill=GOLD, outline=INK, width: float = 3, rot: float = -90) -> None:
    p.setPen(QPen(qc(outline), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin) if outline is not None else Qt.NoPen)
    p.setBrush(qc(fill))
    p.drawPath(star_path(cx, cy, r, rot=rot))


def cloud(p: QPainter, cx: float, cy: float, s: float, color=WHITE) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(qc(color))
    for dx, dy, r in ((-0.55, 0.1, 0.38), (-0.2, -0.18, 0.5), (0.25, -0.1, 0.45), (0.6, 0.12, 0.34), (0.05, 0.18, 0.42)):
        p.drawEllipse(QPointF(cx + dx * s, cy + dy * s), r * s, r * s)


def vgrad(top, bottom, y0: float = 0, y1: float = H) -> QLinearGradient:
    g = QLinearGradient(0, y0, 0, y1)
    g.setColorAt(0, qc(top))
    g.setColorAt(1, qc(bottom))
    return g


def word_card(p: QPainter, word: str, cx: float, cy: float, w: float, h: float, fill=WHITE, ink=INK,
              border="#2d2840", size: float | None = None, radius: float = 22, shadow: float = 6) -> None:
    r = QRectF(cx - w / 2, cy - h / 2, w, h)
    rounded(p, r, radius, fill, border, 4, shadow=shadow)
    text(p, word, cx, cy, size or h * 0.42, ink, max_w=w - 30)


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    color: QColor
    shape: str = "dot"  # dot | star | rect
    spin: float = 0
    rot: float = 0
    gravity: float = 600


@dataclass
class Floater:
    text: str
    x: float
    y: float
    color: QColor
    size: float
    life: float = 1.1
    age: float = 0


@dataclass
class CanvasButton:
    rect: QRectF
    label: str
    color: str
    on_click: Callable[[], None]
    hover: bool = False
    visible: bool = True
    size: float = 22
    icon: str = ""


# ---------------------------------------------------------------------------
# Base game canvas
# ---------------------------------------------------------------------------

BACKDROPS = {
    # name: (top, bottom, decoration kind)
    "sky": ("#8fd3ff", "#e6f6ff", "clouds"),
    "space": ("#2a2363", "#6a4fc4", "stars"),
    "sea": ("#4cc3f0", "#1f6fb8", "bubbles"),
    "forest": ("#b8ecb0", "#5fb86a", "leaves"),
    "candy": ("#ffd6f0", "#c99aff", "sparkles"),
    "sunset": ("#ffd18a", "#ff7f7f", "clouds"),
    "meadow": ("#9be0ff", "#d7f5c4", "clouds"),
}


class GameCanvas(QWidget):
    key_name = ""
    title = ""
    backdrop = "sky"
    instructions = ""
    # Score thresholds for 1, 2 and 3 stars (for lower-is-better games the
    # thresholds are maximums).
    star_thresholds = (1, 2, 3)
    lower_is_better = False

    def __init__(self, words: list[str], on_finish: Callable[[float, list[str], int], None] | None = None,
                 on_exit: Callable[[], None] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(640, 440)
        self.words = [w for w in words if w.strip()]
        self.on_finish = on_finish
        self.on_exit = on_exit
        self.rng = random.Random()
        self.t = 0.0
        self.particles: list[Particle] = []
        self.floaters: list[Floater] = []
        self.buttons: list[CanvasButton] = []
        self.overlay_buttons: list[CanvasButton] = []
        self.shake = 0.0
        self.state = "intro"  # intro -> play -> done
        self.state_t = 0.0
        self.score = 0.0
        self.result_lines: list[str] = []
        self.result_stars = 0
        self.timer_total = 0.0
        self.timer_left = 0.0
        self.hud_extra = ""
        self.previous_best: float | None = None  # set by the arcade, for the 'New best!' line
        self._deco = self._make_deco()
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._frame)
        self._timer.start(16)
        self.restart()

    # -- lifecycle --------------------------------------------------------
    def restart(self) -> None:
        self.particles.clear()
        self.floaters.clear()
        self.buttons.clear()
        self.overlay_buttons.clear()
        self.state = "intro"
        self.state_t = 0.0
        self.score = 0
        self.result_lines = []
        self.result_stars = 0
        self.timer_total = self.timer_left = 0.0
        self.start_game()
        self._last_count = None

    def start_game(self) -> None:  # pragma: no cover - overridden
        pass

    def tick(self, dt: float) -> None:  # pragma: no cover - overridden
        pass

    def draw_game(self, p: QPainter) -> None:  # pragma: no cover - overridden
        pass

    def click(self, x: float, y: float) -> None:  # pragma: no cover - overridden
        pass

    def key(self, k: int) -> None:
        pass

    def hover_move(self, x: float, y: float) -> None:
        pass

    def stars_for(self, score: float) -> int:
        a, b, c = self.star_thresholds
        if self.lower_is_better:
            return 3 if score <= c else 2 if score <= b else 1 if score <= a else 0
        return 3 if score >= c else 2 if score >= b else 1 if score >= a else 0

    def finish(self, score: float, lines: list[str]) -> None:
        if self.state == "done":
            return
        self.state = "done"
        self.state_t = 0.0
        self.score = score
        self.result_lines = list(lines)
        self.result_stars = max(1, self.stars_for(score))
        self.new_best = False
        if self.previous_best is None:
            self.result_lines.append("First go - that's your score to beat!")
        else:
            better = score < self.previous_best if self.lower_is_better else score > self.previous_best
            self.new_best = better
            self.result_lines.append("New best score!" if better else f"Your best so far: {self.previous_best:g}")
        if self.new_best or self.previous_best is None:
            self.previous_best = score  # so "Play again" compares against this go
        self.buttons.clear()
        sound.play("win")
        for _ in range(6):
            self.burst(self.rng.uniform(100, 900), self.rng.uniform(80, 300), RAINBOW, 22, shape="rect", speed=380)
        self.overlay_buttons = [
            CanvasButton(QRectF(W / 2 - 250, 495, 240, 74), "Play again", "#ff9f1c", self.restart, icon="↻"),
            CanvasButton(QRectF(W / 2 + 10, 495, 240, 74), "Arcade", "#3fa7e8", self._exit, icon="⌂"),
        ]
        if self.on_finish:
            self.on_finish(score, lines, self.result_stars)

    def _exit(self) -> None:
        if self.on_exit:
            self.on_exit()

    def start_timer(self, seconds: float) -> None:
        self.timer_total = self.timer_left = seconds

    # -- effects ----------------------------------------------------------
    def burst(self, x: float, y: float, colors, n: int = 18, shape: str = "dot", speed: float = 260,
              size: float = 7, gravity: float = 500) -> None:
        for _ in range(n):
            a = self.rng.uniform(0, 2 * math.pi)
            v = self.rng.uniform(speed * 0.35, speed)
            life = self.rng.uniform(0.5, 1.0)
            self.particles.append(Particle(
                x, y, math.cos(a) * v, math.sin(a) * v - speed * 0.3, life, life,
                self.rng.uniform(size * 0.6, size * 1.4), qc(self.rng.choice(list(colors))), shape,
                self.rng.uniform(-8, 8), self.rng.uniform(0, 6.28), gravity,
            ))

    def float_text(self, s: str, x: float, y: float, color=GOOD, size: float = 30) -> None:
        self.floaters.append(Floater(s, x, y, qc(color), size))

    def good(self, x: float, y: float, label: str = "+1") -> None:
        sound.play("good")
        self.burst(x, y, ["#ffd43b", "#78cd5a", "#46b9e6", "#ffffff"], 26, shape="star", size=9)
        self.float_text(label, x, y - 30, GOOD, 34)

    def bad(self, x: float, y: float, label: str = "Oops!") -> None:
        sound.play("bad")
        self.shake = 0.25
        self.float_text(label, x, y - 30, BAD, 28)

    # -- frame loop -------------------------------------------------------
    def _frame(self) -> None:
        now = self._clock.elapsed()
        dt = min(0.05, (now - self._last) / 1000.0) if self._last else 0.016
        self._last = now
        self.advance(dt)
        self.update()

    def advance(self, dt: float) -> None:
        """Move the game on by `dt` seconds (the frame timer calls this;
        tests call it directly to fast-forward)."""
        self.t += dt
        self.state_t += dt
        self.shake = max(0.0, self.shake - dt)

        if self.state == "intro":
            count = 3 - int(self.state_t / 0.7)
            if count != getattr(self, "_last_count", None) and count >= 0:
                self._last_count = count
                sound.play("tick" if count > 0 else "go")
            if self.state_t >= 0.7 * 3 + 0.5:
                self.state = "play"
                self.state_t = 0.0
        elif self.state == "play":
            if self.timer_total:
                self.timer_left = max(0.0, self.timer_left - dt)
            self.tick(dt)
        else:
            if self.rng.random() < 0.15:
                self.burst(self.rng.uniform(80, 920), -10, RAINBOW, 3, shape="rect", speed=90, gravity=220)

        for pt in self.particles:
            pt.life -= dt
            pt.vy += pt.gravity * dt
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            pt.rot += pt.spin * dt
        self.particles = [pt for pt in self.particles if pt.life > 0]
        for fl in self.floaters:
            fl.age += dt
        self.floaters = [fl for fl in self.floaters if fl.age < fl.life]

    # -- geometry ---------------------------------------------------------
    def _transform(self) -> tuple[float, float, float]:
        s = min(self.width() / W, self.height() / H)
        ox = (self.width() - W * s) / 2
        oy = (self.height() - H * s) / 2
        return s, ox, oy

    def to_design(self, pos) -> tuple[float, float]:
        s, ox, oy = self._transform()
        return (pos.x() - ox) / s, (pos.y() - oy) / s

    # -- painting ---------------------------------------------------------
    def _make_deco(self) -> list[list[float]]:
        rng = random.Random(hash(self.backdrop) & 0xFFFF)
        return [[rng.uniform(-100, W + 100), rng.uniform(-60, H + 60), rng.uniform(0.6, 1.4), rng.uniform(0, 6.28)]
                for _ in range(26)]

    def _draw_backdrop(self, p: QPainter, s: float, ox: float, oy: float) -> None:
        top, bottom, kind = BACKDROPS[self.backdrop]
        # Fill the *whole* widget (beyond the design area too), so wide or
        # tall windows never show bare bars.
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, qc(top))
        g.setColorAt(1, qc(bottom))
        p.fillRect(self.rect(), g)
        p.save()
        p.translate(ox, oy)
        p.scale(s, s)
        ext_x0, ext_x1 = -ox / s, (self.width() - ox) / s
        ext_y0, ext_y1 = -oy / s, (self.height() - oy) / s
        span_x = ext_x1 - ext_x0 + 300
        span_y = ext_y1 - ext_y0 + 200
        for i, (x, y, k, ph) in enumerate(self._deco):
            if kind == "clouds":
                if i % 3:
                    continue
                cx = ext_x0 - 150 + (x + self.t * 18 * k) % span_x
                cloud(p, cx, y * 0.45 + ext_y0 + 30, 60 * k, QColor(255, 255, 255, 200))
            elif kind == "stars":
                tw = 0.5 + 0.5 * math.sin(self.t * 2.5 * k + ph)
                cx = ext_x0 + (x - ext_x0) % (ext_x1 - ext_x0 + 1)
                star(p, cx, ext_y0 + (y % (ext_y1 - ext_y0 + 1)), 5 + 5 * k * tw, QColor(255, 240, 180, int(120 + 120 * tw)),
                     None, 0)
            elif kind == "bubbles":
                cy = ext_y1 + 40 - (y + self.t * 40 * k) % span_y
                cx = x + math.sin(self.t * 1.5 + ph) * 12
                circle(p, cx, cy, 6 + 8 * k, QColor(255, 255, 255, 60), QColor(255, 255, 255, 150), 2)
            elif kind == "leaves":
                cy = ext_y0 - 40 + (y + self.t * 30 * k) % span_y
                cx = x + math.sin(self.t + ph) * 30
                p.save()
                p.translate(cx, cy)
                p.rotate(math.degrees(self.t * k + ph))
                ellipse(p, 0, 0, 12 * k, 6 * k, QColor(120, 200, 90, 150))
                p.restore()
            elif kind == "sparkles":
                tw = 0.5 + 0.5 * math.sin(self.t * 3 * k + ph)
                star(p, x, y, 4 + 6 * tw, QColor(255, 255, 255, int(90 + 140 * tw)), None, 0, rot=self.t * 40)
        p.restore()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        s, ox, oy = self._transform()
        self._draw_backdrop(p, s, ox, oy)

        p.save()
        if self.shake > 0:
            amp = 10 * self.shake / 0.25
            p.translate(self.rng.uniform(-amp, amp), self.rng.uniform(-amp, amp))
        p.translate(ox, oy)
        p.scale(s, s)
        self.draw_game(p)
        self._draw_buttons(p, self.buttons)
        self._draw_effects(p)
        self._draw_hud(p)
        if self.state == "intro":
            self._draw_intro(p)
        elif self.state == "done":
            self._draw_results(p)
        p.restore()
        p.end()

    def _draw_effects(self, p: QPainter) -> None:
        for pt in self.particles:
            a = max(0.0, pt.life / pt.max_life)
            c = QColor(pt.color)
            c.setAlphaF(a)
            if pt.shape == "star":
                star(p, pt.x, pt.y, pt.size * (0.6 + 0.4 * a), c, None, 0, rot=math.degrees(pt.rot))
            elif pt.shape == "rect":
                p.save()
                p.translate(pt.x, pt.y)
                p.rotate(math.degrees(pt.rot))
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRect(QRectF(-pt.size / 2, -pt.size / 4, pt.size, pt.size / 2))
                p.restore()
            else:
                circle(p, pt.x, pt.y, pt.size * a, c)
        for fl in self.floaters:
            k = fl.age / fl.life
            c = QColor(fl.color)
            c.setAlphaF(max(0.0, 1 - k ** 2))
            o = QColor(255, 255, 255)
            o.setAlphaF(c.alphaF())
            text(p, fl.text, fl.x, fl.y - 70 * ease_out_cubic(k), fl.size * (0.8 + 0.4 * ease_out_back(min(1, k * 4))),
                 c, o, 6)

    def _draw_hud(self, p: QPainter) -> None:
        # Title pill (left), score pill (right), timer bar (top).
        rounded(p, QRectF(14, 12, 300, 52), 26, QColor(255, 255, 255, 225), INK, 3)
        text(p, self.title, 164, 38, 20, INK, max_w=270)
        right = self.hud_text()
        if right:
            rounded(p, QRectF(W - 254, 12, 240, 52), 26, QColor(255, 255, 255, 225), INK, 3)
            text(p, right, W - 134, 38, 20, INK, max_w=215)
        if self.timer_total:
            frac = self.timer_left / self.timer_total
            bar = QRectF(330, 26, W - 600, 24)
            rounded(p, bar, 12, QColor(255, 255, 255, 170), INK, 3)
            col = "#2ec97a" if frac > 0.5 else "#ffb703" if frac > 0.2 else "#ff5d73"
            if frac > 0:
                rounded(p, QRectF(bar.x() + 3, bar.y() + 3, (bar.width() - 6) * frac, bar.height() - 6), 9, col)
            text(p, f"{math.ceil(self.timer_left)}s", bar.center().x(), bar.center().y(), 13, INK)

    def hud_text(self) -> str:
        return ""

    def _draw_intro(self, p: QPainter) -> None:
        p.fillRect(QRectF(-2000, -2000, 5000, 5000), QColor(20, 15, 40, 110))
        card = QRectF(W / 2 - 330, 150, 660, 380)
        rounded(p, card, 36, WHITE, INK, 5, shadow=10)
        text(p, self.title, W / 2, 215, 40, "#ff6363", INK, 8, max_w=600)
        lines = self.instructions.split("\n")
        for i, line in enumerate(lines):
            text(p, line, W / 2, 285 + i * 38, 19, INK, bold=False, max_w=600)
        count = 3 - int(self.state_t / 0.7)
        label = str(count) if count > 0 else "GO!"
        k = (self.state_t % 0.7) / 0.7
        size = 70 * ease_out_back(min(1.0, k * 2.5))
        circle(p, W / 2, 455, 58, "#ffcc33", INK, 5)
        if size > 1:
            text(p, label, W / 2, 458, size * 0.75, WHITE, INK, 6)

    def _draw_results(self, p: QPainter) -> None:
        k = ease_out_back(min(1.0, self.state_t * 2.2))
        p.fillRect(QRectF(-2000, -2000, 5000, 5000), QColor(20, 15, 40, int(110 * min(1, self.state_t * 3))))
        p.save()
        p.translate(W / 2, H / 2)
        p.scale(k, k)
        p.translate(-W / 2, -H / 2)
        card = QRectF(W / 2 - 340, 90, 680, 500)
        rounded(p, card, 40, WHITE, INK, 5, shadow=12)
        msgs = {3: "Amazing!", 2: "Great job!", 1: "Nice work!", 0: "Good try!"}
        text(p, msgs[self.result_stars], W / 2, 158, 44, "#ff9f1c", INK, 8)
        for i in range(3):
            sx = W / 2 + (i - 1) * 120
            delay = 0.35 + i * 0.25
            sk = ease_out_back(min(1.0, max(0.0, (self.state_t - delay) * 3)))
            if i < self.result_stars and sk > 0:
                if not hasattr(self, "_star_sound") or self._star_sound < i + 1:
                    if self.state_t > delay:
                        self._star_sound = i + 1
                        sound.play("star")
                star(p, sx, 270 - (14 if i == 1 else 0), 52 * sk, GOLD, INK, 5)
            else:
                star(p, sx, 270 - (14 if i == 1 else 0), 52, QColor(225, 225, 235), QColor(180, 180, 195), 4)
        for i, line in enumerate(self.result_lines):
            is_best = line == "New best score!"
            if is_best:
                rounded(p, QRectF(W / 2 - 170, 370 + i * 44 - 22, 340, 44), 22, "#fff1b8", "#ffb703", 3)
            text(p, line, W / 2, 370 + i * 44, 24 if not is_best else 26, "#c2410c" if is_best else INK, max_w=620)
        p.restore()
        if self.state_t > 0.4:
            self._draw_buttons(p, self.overlay_buttons)

    def _draw_buttons(self, p: QPainter, buttons: list[CanvasButton]) -> None:
        for b in buttons:
            if not b.visible:
                continue
            r = QRectF(b.rect)
            lift = -3 if b.hover else 0
            col = qc(b.color)
            rounded(p, r.translated(0, 6), r.height() / 2.6, col.darker(140))
            rounded(p, r.translated(0, lift), r.height() / 2.6, col.lighter(108) if b.hover else col, INK, 3)
            label = f"{b.icon}  {b.label}" if b.icon else b.label
            text(p, label, r.center().x(), r.center().y() + lift, b.size, WHITE, col.darker(170), 5, max_w=r.width() - 20)

    # -- input ------------------------------------------------------------
    def _all_buttons(self) -> list[CanvasButton]:
        return self.overlay_buttons if self.state == "done" else self.buttons

    def mousePressEvent(self, event) -> None:
        x, y = self.to_design(event.position())
        if self.state == "done":
            if self.state_t > 0.4:
                for b in self.overlay_buttons:
                    if b.visible and b.rect.contains(x, y):
                        sound.play("click")
                        b.on_click()
                        return
            return
        if self.state != "play":
            return
        for b in self.buttons:
            if b.visible and b.rect.contains(x, y):
                b.on_click()
                return
        self.click(x, y)

    def mouseMoveEvent(self, event) -> None:
        x, y = self.to_design(event.position())
        any_hover = False
        for b in self._all_buttons():
            b.hover = b.visible and b.rect.contains(x, y)
            any_hover = any_hover or b.hover
        self.setCursor(Qt.PointingHandCursor if any_hover else Qt.ArrowCursor)
        if self.state == "play":
            self.hover_move(x, y)

    def keyPressEvent(self, event) -> None:
        if self.state == "play":
            self.key(event.key())
        elif self.state == "done" and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and self.state_t > 0.6:
            self.restart()
        super().keyPressEvent(event)

    def stop(self) -> None:
        self._timer.stop()
