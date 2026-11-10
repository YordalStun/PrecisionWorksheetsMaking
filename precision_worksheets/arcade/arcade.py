"""The Word Arcade: a bright, full-window hub of big game tiles, and the
window the games play in.

`ArcadeWindow` is what the rest of the app opens (from the big "Play
games" button on a child's page, or a tile on the Games tab). It shows the
hub; picking a tile swaps the hub for that game, and the game's results
card has an "Arcade" button that swaps straight back - no dialogs
stacked on dialogs, and no forms in the way of playing.
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QRectF, Qt, QTimer, QElapsedTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QStackedWidget, QVBoxLayout, QWidget

from . import sound
from .engine import (
    GOLD,
    H,
    INK,
    RAINBOW,
    W,
    WHITE,
    circle,
    cloud,
    ease_out_back,
    ellipse,
    qc,
    rounded,
    star,
    text,
)
from .games import (
    GAME_CLASSES,
    draw_apple,
    draw_balloon,
    draw_basket,
    draw_fish,
    draw_mole,
    draw_owl,
    draw_rocket,
    draw_train_engine,
)


@dataclass(frozen=True)
class GameInfo:
    key: str
    title: str
    blurb: str
    metric: str
    lower_is_better: bool
    color_top: str
    color_bottom: str


# Order = order on the hub. Keys and metrics of the first five match the
# original games, so earlier saved scores still count.
GAMES: list[GameInfo] = [
    GameInfo("flash", "Rocket Blitz", "Read fast, blast off!", "/min", False, "#5b4bd6", "#9b7cf0"),
    GameInfo("pop", "Bubble Pop", "Pop the right word", "/8", False, "#2fa8e6", "#7fd6ff"),
    GameInfo("whack", "Whack-a-Word", "Bonk the right mole", " bonks", False, "#4fae3d", "#9be07a"),
    GameInfo("catch", "Word Catcher", "Catch the right apples", " caught", False, "#ff8a3d", "#ffc56b"),
    GameInfo("memory", "Memory Match", "Find the pairs", " moves", True, "#d0549c", "#ff9fd0"),
    GameInfo("peek", "Peekaboo Owl", "Remember the word", "/10", False, "#2e8b57", "#7fd18f"),
    GameInfo("scramble", "Letter Train", "Build the word", " oops", True, "#e0484f", "#ff8f8f"),
]
GAMES_BY_KEY = {g.key: g for g in GAMES}


def draw_game_icon(p: QPainter, key: str, cx: float, cy: float, s: float, t: float) -> None:
    """The picture on each hub tile (s = rough size of the picture)."""
    if key == "flash":
        for i in range(5):
            star(p, cx - s * 0.45 + i * s * 0.22, cy - s * 0.35 + (i % 2) * s * 0.5, 6, QColor(255, 240, 180), None, 0)
        draw_rocket(p, cx, cy + math.sin(t * 3) * 6, s * 0.75, 0.6, t=t)
    elif key == "pop":
        for dx, dy, r in ((-0.3, -0.15, 0.2), (0.32, -0.25, 0.15), (0.3, 0.25, 0.12)):
            circle(p, cx + dx * s, cy + dy * s + math.sin(t * 2 + dx * 9) * 5, r * s, QColor(255, 255, 255, 80), WHITE, 3)
        draw_fish(p, cx - s * 0.05, cy + s * 0.12, s * 0.55, "#ff9f1c", 1, t, 1)
    elif key == "whack":
        ellipse(p, cx, cy + s * 0.32, s * 0.42, s * 0.12, "#4a2e1f", INK, 3)
        p.save()
        p.setClipRect(QRectF(cx - s, cy - s, 2 * s, s * 1.32))
        draw_mole(p, cx, cy + s * 0.12 - abs(math.sin(t * 2)) * s * 0.12, s * 0.62, 0, t)
        p.restore()
        p.setPen(QPen(INK, 3))
        p.setBrush(QColor("#7a4f35"))
        p.drawChord(QRectF(cx - s * 0.45, cy + s * 0.2, s * 0.9, s * 0.26), 180 * 16, 180 * 16)
    elif key == "catch":
        draw_apple(p, cx - s * 0.18, cy - s * 0.25 + (t * 40 % 30), s * 0.13, "#ff5d5d")
        draw_apple(p, cx + s * 0.22, cy - s * 0.4 + ((t * 40 + 15) % 30), s * 0.11, "#8bd346")
        draw_basket(p, cx, cy + s * 0.25, s * 0.6, math.sin(t * 2) * 6)
    elif key == "memory":
        for i, (dx, rot) in enumerate(((-0.2, -12), (0.2, 12))):
            p.save()
            p.translate(cx + dx * s, cy + math.sin(t * 2 + i) * 4)
            p.rotate(rot)
            r = QRectF(-s * 0.2, -s * 0.27, s * 0.4, s * 0.54)
            rounded(p, r, 10, RAINBOW[i * 3] if i == 0 else WHITE, INK, 3)
            if i == 0:
                star(p, 0, 0, s * 0.1, WHITE, INK, 2)
            else:
                text(p, "cat", 0, 0, s * 0.1, INK)
            p.restore()
    elif key == "peek":
        draw_owl(p, cx, cy + s * 0.05, s * 0.6, eyes_closed=(t % 2) < 1, t=t)
    elif key == "scramble":
        draw_train_engine(p, cx - s * 0.32, cy + s * 0.38, s * 0.55, t, True)
        draw_balloon(p, cx + s * 0.3, cy - s * 0.25, s * 0.13, "#46b9e6", "a", t, 0)
        draw_balloon(p, cx + s * 0.05, cy - s * 0.38, s * 0.12, "#ff78be", "b", t, 2)


class HubCanvas(QWidget):
    """The arcade's front page: a bouncy title, this week's words, and a
    big animated tile per game (best score + stars on each)."""

    def __init__(self, child_name: str, words_provider: Callable[[], list[str]],
                 scores_provider: Callable[[], dict], on_pick: Callable[[str], None],
                 compact: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.child_name = child_name
        self.words_provider = words_provider
        self.scores_provider = scores_provider
        self.on_pick = on_pick
        self.compact = compact
        self.setMouseTracking(True)
        self.setMinimumSize(560, 360 if compact else 420)
        self.hover = None
        self.t = 0.0
        self._scores: dict = {}
        self.refresh()
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def refresh(self) -> None:
        self._scores = self.scores_provider() or {}
        self.update()

    def _tick(self) -> None:
        self.t = self._clock.elapsed() / 1000.0
        if self.isVisible():
            self.update()

    # Layout in design space: tiles in a 4 x 2 grid (7 games + Surprise).
    def _tile_rects(self) -> list[tuple[str, QRectF]]:
        keys = [g.key for g in GAMES] + ["surprise"]
        cols, rows = 4, 2
        top = 120 if self.compact else 205
        gap = 18
        tw = (W - 40 - gap * (cols - 1)) / cols
        th = (H - top - 20 - gap * (rows - 1)) / rows
        out = []
        for i, k in enumerate(keys):
            r, c = divmod(i, cols)
            out.append((k, QRectF(20 + c * (tw + gap), top + r * (th + gap), tw, th)))
        return out

    def _transform(self):
        s = min(self.width() / W, self.height() / H)
        return s, (self.width() - W * s) / 2, (self.height() - H * s) / 2

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = __import__("PySide6.QtGui", fromlist=["QLinearGradient"]).QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor("#ffe3f3"))
        g.setColorAt(0.5, QColor("#e3f1ff"))
        g.setColorAt(1, QColor("#e6ffe9"))
        p.fillRect(self.rect(), g)
        s, ox, oy = self._transform()
        p.translate(ox, oy)
        p.scale(s, s)
        # Drifting clouds behind everything.
        for i in range(5):
            x = (i * 260 + self.t * (12 + i * 3)) % (W + 300) - 150
            cloud(p, x, 60 + (i % 3) * 30 + (0 if not self.compact else -20), 46 + i * 4, QColor(255, 255, 255, 190))

        if not self.compact:
            self._draw_title(p, "Word Arcade", 72, 58)
            hello = f"Hi {self.child_name}! Pick a game." if self.child_name else "Pick a game!"
            text(p, hello, W / 2, 135, 22, "#6b5ca5")
            self._draw_words(p, 175)
        else:
            self._draw_words(p, 50, label="This week's words:")
            text(p, "Tap a game to play!", W / 2, 95, 20, "#6b5ca5")

        for i, (key, r) in enumerate(self._tile_rects()):
            self._draw_tile(p, key, r, i)

    def _draw_title(self, p: QPainter, title: str, cy: float, size: float) -> None:
        f_w = 0
        from .engine import fit_size, font
        from PySide6.QtGui import QFontMetricsF

        fm = QFontMetricsF(font(size))
        total = sum(fm.horizontalAdvance(ch) for ch in title) + 4 * len(title)
        x = W / 2 - total / 2
        for i, ch in enumerate(title):
            w = fm.horizontalAdvance(ch)
            if ch != " ":
                bob = math.sin(self.t * 3 + i * 0.6) * 6
                p.save()
                p.translate(x + w / 2, cy + bob)
                p.rotate(math.sin(self.t * 2 + i) * 5)
                text(p, ch, 0, 0, size, RAINBOW[i % 7], INK, 9)
                p.restore()
            x += w + 4

    def _draw_words(self, p: QPainter, cy: float, label: str = "Our words:") -> None:
        words = self.words_provider() or []
        from .engine import font
        from PySide6.QtGui import QFontMetricsF

        size = 18.0
        while True:
            fm = QFontMetricsF(font(size))
            widths = [fm.horizontalAdvance(w) + 34 for w in words]
            lw = QFontMetricsF(font(size * 0.9)).horizontalAdvance(label) + 14
            total = lw + sum(widths) + 10 * max(0, len(words) - 1)
            if total < W - 80 or size <= 10:
                break
            size -= 1
        x = W / 2 - total / 2
        text(p, label, x, cy, size * 0.9, "#6b5ca5", align="left")
        x += lw
        for i, (w, wd) in enumerate(zip(words, widths)):
            col = qc(RAINBOW[i % 7]).lighter(150)
            rounded(p, QRectF(x, cy - size, wd, size * 2), size, col, qc(RAINBOW[i % 7]).darker(130), 3)
            text(p, w, x + wd / 2, cy, size, INK)
            x += wd + 10

    def _draw_tile(self, p: QPainter, key: str, r: QRectF, i: int) -> None:
        hover = self.hover == key
        lift = -8 if hover else 0
        k = 1.03 if hover else 1.0
        p.save()
        p.translate(r.center().x(), r.center().y() + lift)
        p.scale(k, k)
        rr = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
        from PySide6.QtGui import QLinearGradient

        if key == "surprise":
            top, bottom, title, blurb = "#ffcc33", "#ff9f1c", "Surprise me!", "Pick a random game"
        else:
            info = GAMES_BY_KEY[key]
            top, bottom, title, blurb = info.color_top, info.color_bottom, info.title, info.blurb
        g = QLinearGradient(0, rr.top(), 0, rr.bottom())
        g.setColorAt(0, qc(top))
        g.setColorAt(1, qc(bottom))
        rounded(p, rr.translated(0, 8), 26, qc(top).darker(150))
        rounded(p, rr, 26, g, INK, 4)
        # Picture area (top ~half), then title, then stars/best or blurb.
        pad = 12
        pic_h = rr.height() * 0.5
        rounded(p, QRectF(rr.left() + pad, rr.top() + pad, rr.width() - 2 * pad, pic_h), 18, QColor(255, 255, 255, 70))
        pcx, pcy = 0, rr.top() + pad + pic_h / 2
        if key == "surprise":
            for j in range(3):
                a = self.t * 1.5 + j * 2.1
                star(p, pcx + math.cos(a) * 45, pcy + math.sin(a) * 25, 22, RAINBOW[j * 2], INK, 3)
            text(p, "?", pcx, pcy, 54, WHITE, INK, 8)
        else:
            draw_game_icon(p, key, pcx, pcy, min(pic_h, rr.width()) * 0.95, self.t + i)
        below_top = rr.top() + pad + pic_h
        below_h = rr.bottom() - below_top
        title_y = below_top + below_h * 0.3
        text(p, title, 0, title_y, 22, WHITE, qc(top).darker(170), 6, max_w=rr.width() - 20)
        if key != "surprise" and key in self._scores:
            best, plays = self._scores[key]
            info = GAMES_BY_KEY[key]
            cls = GAME_CLASSES[key]
            stars = _stars_for(cls, best, len(self.words_provider() or []) or 5)
            star_y = below_top + below_h * 0.6
            for j in range(3):
                star(p, -30 + j * 30, star_y, 12, GOLD if j < stars else QColor(255, 255, 255, 120), INK, 2)
            text(p, f"Best {best:g}{info.metric}", 0, below_top + below_h * 0.84, 13, INK, max_w=rr.width() - 20)
        else:
            text(p, blurb, 0, below_top + below_h * 0.7, 14, INK, max_w=rr.width() - 20)
        if hover:
            circle(p, rr.right() - 30, rr.top() + 30, 22, WHITE, INK, 3)
            path = QPainterPath()
            cx, cy = rr.right() - 27, rr.top() + 30
            path.moveTo(cx - 7, cy - 10)
            path.lineTo(cx + 10, cy)
            path.lineTo(cx - 7, cy + 10)
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(qc("#2ec97a"))
            p.drawPath(path)
        p.restore()

    def _key_at(self, pos) -> str | None:
        s, ox, oy = self._transform()
        x, y = (pos.x() - ox) / s, (pos.y() - oy) / s
        for key, r in self._tile_rects():
            if r.contains(x, y):
                return key
        return None

    def mouseMoveEvent(self, e) -> None:
        key = self._key_at(e.position())
        if key != self.hover:
            self.hover = key
            self.setCursor(Qt.PointingHandCursor if key else Qt.ArrowCursor)

    def leaveEvent(self, _e) -> None:
        self.hover = None

    def mousePressEvent(self, e) -> None:
        key = self._key_at(e.position())
        if key:
            sound.play("click")
            self.on_pick(key)


def _stars_for(cls, score: float, n_words: int) -> int:
    """Stars for a saved best score, using the game's own thresholds."""
    thresholds = cls.star_thresholds
    if cls.key_name == "memory":
        thresholds = (n_words * 3, n_words * 2, round(n_words * 1.4))
    a, b, c = thresholds
    if cls.lower_is_better:
        return 3 if score <= c else 2 if score <= b else 1 if score <= a else 0
    return 3 if score >= c else 2 if score >= b else 1 if score >= a else 0


class ArcadeWindow(QDialog):
    """The arcade: hub and games in one big window."""

    def __init__(self, parent, conn, child_id: int, child_name: str, words: list[str], start_game: str | None = None):
        super().__init__(parent)
        self.conn = conn
        self.child_id = child_id
        self.words = list(words)
        self.setWindowTitle("Word Arcade")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        self.resize(1180, 820)
        self.setStyleSheet("QDialog { background: #e3f1ff; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.hub = HubCanvas(child_name, lambda: self.words, self._scores, self.play)
        self.stack.addWidget(self.hub)
        self.game: QWidget | None = None
        self._rng = __import__("random").Random()
        if start_game:
            QTimer.singleShot(0, lambda: self.play(start_game))

    def _scores(self) -> dict:
        from ..games_ui import best_scores

        return best_scores(self.conn, self.child_id)

    def play(self, key: str) -> None:
        if key == "surprise":
            key = self._rng.choice([g.key for g in GAMES])
        cls = GAME_CLASSES[key]
        if self.game is not None:
            self.game.stop()
            self.stack.removeWidget(self.game)
            self.game.deleteLater()
        self.game = cls(self.words, on_finish=lambda score, lines, stars, k=key: self._record(k, score),
                        on_exit=self.show_hub)
        best = self._scores().get(key)
        self.game.previous_best = best[0] if best else None
        self.stack.addWidget(self.game)
        self.stack.setCurrentWidget(self.game)
        self.game.setFocus()

    def _record(self, key: str, score: float) -> None:
        from .. import db

        info = GAMES_BY_KEY[key]
        date_str = datetime.date.today().strftime("%d/%m/%Y")
        db.record_game_score(self.conn, self.child_id, key, date_str, score, info.metric)

    def show_hub(self) -> None:
        if self.game is not None:
            self.game.stop()
        self.hub.refresh()
        self.stack.setCurrentWidget(self.hub)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape and self.stack.currentWidget() is not self.hub:
            self.show_hub()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e) -> None:
        if self.game is not None:
            self.game.stop()
        super().closeEvent(e)
