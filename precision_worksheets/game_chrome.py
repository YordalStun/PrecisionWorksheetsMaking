"""Shared "look and feel" for the mini-games: a colourful gradient theme
per game, big friendly buttons, and a confetti burst on finishing - so a
game dialog reads as a game, not a form."""

from __future__ import annotations

import random

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QPushButton, QWidget

# Per-game palette: a vertical background gradient, an accent colour for
# primary buttons, a darker shade for their pressed/hover state, and the
# ink colour for text on that background.
GAME_THEMES = {
    "flash": {
        "bg_top": "#ffe9a8", "bg_bottom": "#ff9f4d", "accent": "#e8571c",
        "accent_dark": "#c2430f", "ink": "#3a2200", "confetti": ["#ffd166", "#ff9f4d", "#e8571c", "#ffffff"],
    },
    "pop": {
        "bg_top": "#b9ecff", "bg_bottom": "#3fa7e8", "accent": "#1c7fc2",
        "accent_dark": "#145f93", "ink": "#06304a", "confetti": ["#b9ecff", "#3fa7e8", "#ffd166", "#ffffff"],
    },
    "memory": {
        "bg_top": "#ffd6f0", "bg_bottom": "#c974dd", "accent": "#a541b8",
        "accent_dark": "#7d2f8c", "ink": "#3a0a3f", "confetti": ["#ffd6f0", "#c974dd", "#ffd166", "#ffffff"],
    },
    "peek": {
        "bg_top": "#d4f5c8", "bg_bottom": "#5fb86a", "accent": "#2e8b3d",
        "accent_dark": "#206b2b", "ink": "#0f3314", "confetti": ["#d4f5c8", "#5fb86a", "#ffd166", "#ffffff"],
    },
    "scramble": {
        "bg_top": "#ddd3ff", "bg_bottom": "#7c5ce0", "accent": "#5b3fb8",
        "accent_dark": "#412c8c", "ink": "#1c1240", "confetti": ["#ddd3ff", "#7c5ce0", "#ffd166", "#ffffff"],
    },
}


def apply_theme(dialog, game_key: str) -> dict:
    """Paints the dialog's background with the game's gradient and themes
    every ordinary button/label inside it. Returns the theme dict so
    callers can pull specific colours (e.g. for a correct/wrong flash)."""
    theme = GAME_THEMES[game_key]
    dialog.setStyleSheet(
        f"""
        QDialog {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {theme['bg_top']}, stop:1 {theme['bg_bottom']});
        }}
        QWidget#GameBody {{ background: transparent; }}
        QLabel {{ background: transparent; color: {theme['ink']}; }}
        QPushButton {{
            background: white; color: {theme['ink']};
            border: 2px solid rgba(0,0,0,0.15); border-radius: 14px;
            padding: 12px 20px; font-weight: 700; font-size: 12pt;
        }}
        QPushButton:hover {{ background: #fafafa; }}
        QPushButton:disabled {{ background: rgba(255,255,255,0.55); color: rgba(0,0,0,0.35); }}
        QPushButton#GameAccent {{
            background: {theme['accent']}; color: white; border: none;
            padding: 14px 26px; font-size: 13pt;
        }}
        QPushButton#GameAccent:hover {{ background: {theme['accent_dark']}; }}
        """
    )
    return theme


def big_label_style(theme: dict, size: int = 44) -> str:
    return f"font-size: {size}pt; font-weight: 800; color: {theme['ink']};"


def flash_button(btn: QPushButton, color: str) -> None:
    """One-off colour override for a button (e.g. correct=green/wrong=red)
    that still keeps the shared rounded/bold chrome."""
    btn.setStyleSheet(
        f"background: {color}; color: white; border: none; border-radius: 14px; "
        "padding: 14px 20px; font-weight: 800; font-size: 13pt;"
    )


class ConfettiBurst(QWidget):
    """A short burst of falling confetti rectangles over whatever's behind
    it - purely decorative, stops and removes itself after ~1.6s."""

    def __init__(self, parent: QWidget, colors: list[str]):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(parent.rect())
        self.colors = [QColor(c) for c in colors]
        rng = random.Random()
        self.particles = [
            {
                "x": rng.uniform(0, 1), "y": rng.uniform(-0.25, 0),
                "vx": rng.uniform(-0.15, 0.15), "vy": rng.uniform(0.6, 1.1),
                "size": rng.uniform(7, 15), "color": rng.choice(self.colors),
                "rot": rng.uniform(0, 360), "vrot": rng.uniform(-220, 220),
            }
            for _ in range(80)
        ]
        self._ticks = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(30)
        self.show()
        self.raise_()

    def _tick(self) -> None:
        dt = 0.03
        self._ticks += 1
        for p in self.particles:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["rot"] += p["vrot"] * dt
        self.update()
        if self._ticks > 55:
            self.timer.stop()
            self.hide()
            self.deleteLater()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        for p in self.particles:
            painter.save()
            painter.translate(p["x"] * w, p["y"] * h)
            painter.rotate(p["rot"])
            painter.setBrush(p["color"])
            painter.setPen(Qt.NoPen)
            s = p["size"]
            painter.drawRoundedRect(QRectF(-s / 2, -s / 4, s, s / 2), 2, 2)
            painter.restore()
        painter.end()
