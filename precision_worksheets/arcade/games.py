"""The Word Arcade games. Each one uses the child's current practice
words, plays inside the shared GameCanvas engine (animated backdrop,
countdown, effects, results with stars), and reports a single score that
is saved in the child's game history.

Game keys/metrics for the original five games are unchanged, so scores
recorded before this redesign still count towards each game's best.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from . import sound
from .engine import (
    BAD,
    GOLD,
    GOOD,
    H,
    INK,
    RAINBOW,
    W,
    WHITE,
    CanvasButton,
    GameCanvas,
    circle,
    cloud,
    ease_in_out,
    ease_out_back,
    ease_out_cubic,
    ellipse,
    lerp,
    qc,
    rounded,
    star,
    text,
    vgrad,
    word_card,
)


def _other_words(words: list[str], target: str) -> list[str]:
    others = [w for w in words if w != target]
    return others or [target]


# ---------------------------------------------------------------------------
# Little characters, shared with the arcade hub's tiles
# ---------------------------------------------------------------------------

def draw_rocket(p: QPainter, x: float, y: float, s: float, flame: float = 0.0, body="#f2f4fb", trim="#ff5d73", t: float = 0) -> None:
    if flame > 0:
        fl = s * (0.45 + 0.25 * flame + 0.08 * math.sin(t * 40))
        path = QPainterPath()
        path.moveTo(x - s * 0.16, y + s * 0.42)
        path.quadTo(x, y + s * 0.42 + fl * 1.8, x + s * 0.16, y + s * 0.42)
        path.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ff9f1c"))
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(x - s * 0.08, y + s * 0.42)
        path2.quadTo(x, y + s * 0.42 + fl, x + s * 0.08, y + s * 0.42)
        p.setBrush(QColor("#ffe066"))
        p.drawPath(path2)
    for d in (-1, 1):
        fin = QPainterPath()
        fin.moveTo(x + d * s * 0.2, y + s * 0.05)
        fin.lineTo(x + d * s * 0.42, y + s * 0.45)
        fin.lineTo(x + d * s * 0.18, y + s * 0.4)
        fin.closeSubpath()
        p.setPen(QPen(INK, 3))
        p.setBrush(qc(trim))
        p.drawPath(fin)
    ellipse(p, x, y, s * 0.24, s * 0.52, body, INK, 4)
    nose = QPainterPath()
    nose.moveTo(x - s * 0.2, y - s * 0.3)
    nose.quadTo(x, y - s * 0.75, x + s * 0.2, y - s * 0.3)
    nose.closeSubpath()
    p.setPen(QPen(INK, 4))
    p.setBrush(qc(trim))
    p.drawPath(nose)
    circle(p, x, y - s * 0.05, s * 0.12, "#7fd4ff", INK, 4)
    circle(p, x - s * 0.04, y - s * 0.09, s * 0.035, WHITE)
    rounded(p, QRectF(x - s * 0.23, y + s * 0.3, s * 0.46, s * 0.12), 5, trim, INK, 3)


def draw_fish(p: QPainter, x: float, y: float, s: float, color="#ff9f1c", facing: int = 1, t: float = 0, happy: float = 0) -> None:
    tail_wag = math.sin(t * 8) * 0.12
    tail = QPainterPath()
    tail.moveTo(x - facing * s * 0.35, y)
    tail.lineTo(x - facing * s * 0.7, y - s * (0.32 + tail_wag))
    tail.lineTo(x - facing * s * 0.7, y + s * (0.32 - tail_wag))
    tail.closeSubpath()
    p.setPen(QPen(INK, 4))
    p.setBrush(qc(color).darker(115))
    p.drawPath(tail)
    ellipse(p, x, y, s * 0.5, s * 0.36, color, INK, 4)
    ellipse(p, x - facing * s * 0.05, y + s * 0.12, s * 0.25, s * 0.12, qc(color).lighter(130))
    circle(p, x + facing * s * 0.22, y - s * 0.08, s * 0.11, WHITE, INK, 3)
    circle(p, x + facing * s * 0.25, y - s * 0.07, s * 0.05, INK)
    p.setPen(QPen(INK, 4, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    mouth = QRectF(x + facing * s * 0.28 - s * 0.1, y + s * 0.02, s * 0.2, s * (0.1 + 0.1 * happy))
    p.drawArc(mouth, 200 * 16, 140 * 16)


def draw_owl(p: QPainter, x: float, y: float, s: float, eyes_closed: bool = False, t: float = 0) -> None:
    body = QColor("#b07a4f")
    ellipse(p, x, y, s * 0.55, s * 0.62, body, INK, 5)
    ellipse(p, x, y + s * 0.15, s * 0.38, s * 0.42, "#f3d9b1", INK, 3)
    for d in (-1, 1):
        ear = QPainterPath()
        ear.moveTo(x + d * s * 0.2, y - s * 0.52)
        ear.lineTo(x + d * s * 0.45, y - s * 0.78)
        ear.lineTo(x + d * s * 0.48, y - s * 0.4)
        ear.closeSubpath()
        p.setPen(QPen(INK, 4))
        p.setBrush(body)
        p.drawPath(ear)
    blink = eyes_closed or (t % 3.5) < 0.12
    for d in (-1, 1):
        ex = x + d * s * 0.2
        ey = y - s * 0.25
        circle(p, ex, ey, s * 0.17, WHITE, INK, 4)
        if blink:
            p.setPen(QPen(INK, 5, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(ex - s * 0.1, ey - s * 0.08, s * 0.2, s * 0.14), 200 * 16, 140 * 16)
        else:
            circle(p, ex, ey, s * 0.08, INK)
            circle(p, ex - s * 0.025, ey - s * 0.03, s * 0.025, WHITE)
    beak = QPainterPath()
    beak.moveTo(x - s * 0.07, y - s * 0.13)
    beak.lineTo(x + s * 0.07, y - s * 0.13)
    beak.lineTo(x, y - s * 0.01)
    beak.closeSubpath()
    p.setPen(QPen(INK, 3))
    p.setBrush(QColor("#ffb703"))
    p.drawPath(beak)


def draw_mole(p: QPainter, x: float, y: float, s: float, squish: float = 0, t: float = 0) -> None:
    sy = 1 - 0.25 * squish
    ellipse(p, x, y + s * 0.25 * (1 - sy), s * 0.42, s * 0.5 * sy, "#9c6b4e", INK, 4)
    ellipse(p, x, y + s * 0.18, s * 0.26, s * 0.25 * sy, "#d9b08c")
    for d in (-1, 1):
        if squish > 0.2:
            p.setPen(QPen(INK, 4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x + d * s * 0.2 - s * 0.05, y - s * 0.17), QPointF(x + d * s * 0.2 + s * 0.05, y - s * 0.09))
            p.drawLine(QPointF(x + d * s * 0.2 - s * 0.05, y - s * 0.09), QPointF(x + d * s * 0.2 + s * 0.05, y - s * 0.17))
        else:
            circle(p, x + d * s * 0.15, y - s * 0.14, s * 0.06, INK)
            circle(p, x + d * s * 0.15 - s * 0.02, y - s * 0.16, s * 0.02, WHITE)
        circle(p, x + d * s * 0.27, y - s * 0.02, s * 0.05, QColor(255, 140, 160, 180))
    ellipse(p, x, y - s * 0.02, s * 0.09, s * 0.065, "#ff7aa2", INK, 3)
    rounded(p, QRectF(x - s * 0.06, y + s * 0.04, s * 0.12, s * 0.08), 3, WHITE, INK, 2)


def draw_basket(p: QPainter, x: float, y: float, w: float, tilt: float = 0) -> None:
    p.save()
    p.translate(x, y)
    p.rotate(tilt)
    h = w * 0.42
    path = QPainterPath()
    path.moveTo(-w / 2, -h / 2)
    path.lineTo(w / 2, -h / 2)
    path.lineTo(w * 0.38, h / 2)
    path.lineTo(-w * 0.38, h / 2)
    path.closeSubpath()
    p.setPen(QPen(INK, 4))
    p.setBrush(QColor("#d99a4e"))
    p.drawPath(path)
    p.setPen(QPen(QColor("#a8692b"), 4))
    for i in range(1, 4):
        yy = -h / 2 + h * i / 4
        p.drawLine(QPointF(-w / 2 + w * 0.12 * i / 4, yy), QPointF(w / 2 - w * 0.12 * i / 4, yy))
    rounded(p, QRectF(-w / 2 - 8, -h / 2 - 10, w + 16, 20), 10, "#c0803a", INK, 4)
    p.restore()


def draw_apple(p: QPainter, x: float, y: float, r: float, color="#ff5d5d", t: float = 0) -> None:
    p.setPen(QPen(QColor("#6b4423"), 5, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x, y - r * 0.8), QPointF(x + r * 0.1, y - r * 1.15))
    ellipse(p, x + r * 0.35, y - r * 1.0, r * 0.3, r * 0.14, "#5fbf4a", INK, 2)
    circle(p, x, y, r, color, INK, 4)
    circle(p, x - r * 0.35, y - r * 0.35, r * 0.18, QColor(255, 255, 255, 160))


def draw_train_engine(p: QPainter, x: float, y: float, s: float, t: float = 0, moving: bool = False) -> None:
    """Engine facing right; (x, y) = bottom-left on the rail."""
    wheel_rot = t * 400 if moving else 0
    rounded(p, QRectF(x, y - s * 0.75, s * 0.75, s * 0.55), 10, "#ff5d73", INK, 4)
    rounded(p, QRectF(x + s * 0.05, y - s * 1.15, s * 0.42, s * 0.45), 8, "#46b9e6", INK, 4)
    rounded(p, QRectF(x + s * 0.12, y - s * 1.06, s * 0.26, s * 0.22), 5, "#c8f0ff", INK, 3)
    rounded(p, QRectF(x - s * 0.02, y - s * 1.22, s * 0.52, s * 0.1), 4, "#2d2840")
    rounded(p, QRectF(x + s * 0.58, y - s * 1.05, s * 0.14, s * 0.32), 4, "#2d2840")
    p.setPen(QPen(INK, 4))
    p.setBrush(QColor("#ffcc33"))
    cow = QPainterPath()
    cow.moveTo(x + s * 0.75, y - s * 0.45)
    cow.lineTo(x + s * 0.95, y - s * 0.2)
    cow.lineTo(x + s * 0.75, y - s * 0.2)
    cow.closeSubpath()
    p.drawPath(cow)
    for wx in (x + s * 0.18, x + s * 0.55):
        circle(p, wx, y - s * 0.13, s * 0.13, "#2d2840")
        circle(p, wx, y - s * 0.13, s * 0.06, "#ffcc33")
        p.setPen(QPen(QColor("#ffcc33"), 3))
        a = math.radians(wheel_rot)
        p.drawLine(QPointF(wx, y - s * 0.13), QPointF(wx + math.cos(a) * s * 0.11, y - s * 0.13 + math.sin(a) * s * 0.11))


def draw_balloon(p: QPainter, x: float, y: float, r: float, color, letter: str, t: float = 0, phase: float = 0) -> None:
    sway = math.sin(t * 2 + phase) * 6
    p.setPen(QPen(QColor(80, 80, 90), 2))
    path = QPainterPath()
    path.moveTo(x, y + r * 1.15)
    path.cubicTo(x + 10 + sway, y + r * 1.6, x - 10 - sway, y + r * 2.0, x + sway, y + r * 2.4)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    knot = QPainterPath()
    knot.moveTo(x - 7, y + r * 1.18)
    knot.lineTo(x + 7, y + r * 1.18)
    knot.lineTo(x, y + r * 1.05)
    knot.closeSubpath()
    p.setPen(QPen(INK, 2))
    p.setBrush(qc(color).darker(115))
    p.drawPath(knot)
    ellipse(p, x, y, r, r * 1.12, color, INK, 4)
    ellipse(p, x - r * 0.38, y - r * 0.42, r * 0.18, r * 0.28, QColor(255, 255, 255, 150))
    text(p, letter, x, y + 2, r * 0.95, WHITE, qc(color).darker(170), 6)


# ---------------------------------------------------------------------------
# 1. Rocket Blitz (adult-judged reading, 60 seconds)
# ---------------------------------------------------------------------------

class RocketBlitz(GameCanvas):
    key_name = "flash"
    title = "Rocket Blitz"
    backdrop = "space"
    instructions = "Read the word on the rocket out loud!\nGrown-up: tap Read it! (or →) to blast off,\nor Not yet (←) to try the next one. 60 seconds!"
    star_thresholds = (8, 15, 25)

    def start_game(self) -> None:
        self.ok = 0
        self.er = 0
        self.streak = 0
        self.queue: list[str] = []
        self.word = self._next_word()
        self.rocket_y = 470.0
        self.arrive_t = 1.0
        self.launches: list[dict] = []
        self.wobble = 0.0
        self.card_pop = 1.0
        self.start_timer(60)
        self.buttons = [
            CanvasButton(QRectF(735, 250, 235, 110), "Read it!", "#2ec97a", self._correct, icon="✓", size=28),
            CanvasButton(QRectF(735, 395, 235, 90), "Not yet", "#ff8a5b", self._wrong, icon="↺", size=22),
        ]

    def _next_word(self) -> str:
        if not self.queue:
            self.queue = self.rng.sample(self.words, len(self.words))
            if hasattr(self, "word") and len(self.queue) > 1 and self.queue[-1] == self.word:
                self.queue.insert(0, self.queue.pop())
        return self.queue.pop()

    def hud_text(self) -> str:
        return f"✓ {self.ok}    ✗ {self.er}"

    def _correct(self) -> None:
        self.ok += 1
        self.streak += 1
        sound.play("whoosh")
        self.launches.append({"y": self.rocket_y, "v": -200.0, "word": self.word, "color": RAINBOW[self.ok % 7]})
        self.good(430, 300, f"+1  x{self.streak}!" if self.streak >= 3 else "+1")
        self.word = self._next_word()
        self.arrive_t = 0.0
        self.card_pop = 0.0

    def _wrong(self) -> None:
        self.er += 1
        self.streak = 0
        sound.play("bad")
        self.wobble = 0.5
        self.word = self._next_word()
        self.card_pop = 0.0

    def key(self, k: int) -> None:
        if k in (Qt.Key_Right, Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Y):
            self._correct()
        elif k in (Qt.Key_Left, Qt.Key_Backspace, Qt.Key_N):
            self._wrong()

    def tick(self, dt: float) -> None:
        self.arrive_t = min(1.0, self.arrive_t + dt * 2.2)
        self.card_pop = min(1.0, self.card_pop + dt * 3)
        self.wobble = max(0.0, self.wobble - dt)
        for l in self.launches:
            l["v"] -= 1400 * dt
            l["y"] += l["v"] * dt
            if self.rng.random() < 0.8:
                self.particles.append(self._smoke(430, l["y"] + 90))
        self.launches = [l for l in self.launches if l["y"] > -300]
        if self.timer_left <= 0:
            self.finish(self.ok, [f"{self.ok} words read in a minute", f"Best streak counts! ✗ {self.er} to practise"])

    def _smoke(self, x, y):
        from .engine import Particle
        return Particle(x + self.rng.uniform(-14, 14), y, self.rng.uniform(-30, 30), self.rng.uniform(60, 140), 0.7, 0.7,
                        self.rng.uniform(8, 16), QColor(255, 255, 255, 180), "dot", 0, 0, -50)

    def draw_game(self, p: QPainter) -> None:
        # Moon and launch pad.
        circle(p, 880, 610, 140, "#f6efc2", "#d9cf94", 4)
        for dx, dy, r in ((-40, -50, 22), (40, 20, 15), (-10, 60, 12)):
            circle(p, 880 + dx, 610 + dy, r, "#e5dca8")
        rounded(p, QRectF(300, 600, 260, 40), 12, "#6b6f86", INK, 4)
        # Altitude meter: one notch per word read.
        rounded(p, QRectF(36, 90, 54, 560), 27, QColor(255, 255, 255, 70), WHITE, 3)
        level = min(1.0, self.ok / 30)
        if level > 0:
            rounded(p, QRectF(42, 644 - 548 * level, 42, 548 * level), 21, "#ffcc33")
        for i in range(0, 31, 5):
            yy = 644 - 548 * i / 30
            text(p, str(i), 108, yy, 12, WHITE, align="left")
        star(p, 63, 80, 22, GOLD, INK, 3)

        for l in self.launches:
            draw_rocket(p, 430, l["y"], 170, 1.0, trim=l["color"], t=self.t)
        y = lerp(800, self.rocket_y, ease_out_back(self.arrive_t))
        wob = math.sin(self.t * 50) * 10 * self.wobble
        p.save()
        p.translate(430 + wob, y)
        p.rotate(wob * 0.5)
        draw_rocket(p, 0, 0, 170, 0.25 + 0.15 * math.sin(self.t * 6), trim=RAINBOW[(self.ok + 1) % 7], t=self.t)
        p.restore()

        k = ease_out_back(self.card_pop)
        p.save()
        p.translate(430, 205)
        p.scale(k, k)
        word_card(p, self.word, 0, 0, 560, 170, size=74, border=INK)
        p.restore()
        if self.streak >= 3:
            text(p, f"{self.streak} in a row!", 852, 540, 22, "#ffcc33", INK, 5)


# ---------------------------------------------------------------------------
# 2. Bubble Pop (find and pop the word)
# ---------------------------------------------------------------------------

class BubblePop(GameCanvas):
    key_name = "pop"
    title = "Bubble Pop"
    backdrop = "sea"
    instructions = "Finn the fish wants one word.\nPop the bubble with that word in it!\nSay the word out loud as you pop it."
    star_thresholds = (4, 6, 8)
    ROUNDS = 8
    R = 64

    def start_game(self) -> None:
        self.round = 0
        self.score = 0
        self.bubbles: list[dict] = []
        self.targets = [self.words[i % len(self.words)] for i in range(self.ROUNDS)]
        self.rng.shuffle(self.targets)
        self.target = self.targets[0]
        self.missed = False
        self.happy = 0.0
        self.target_pop = 0.0
        for i in range(7):
            self._spawn(initial=True)

    def hud_text(self) -> str:
        return f"Round {min(self.round + 1, self.ROUNDS)} / {self.ROUNDS}"

    def _spawn(self, initial: bool = False) -> None:
        n_target = sum(1 for b in self.bubbles if b["word"] == self.target and not b["popped"])
        word = self.target if n_target < 2 or self.rng.random() < 0.3 else self.rng.choice(_other_words(self.words, self.target))
        best = None
        for _ in range(40):
            x = self.rng.uniform(330, 930)
            y = self.rng.uniform(170, 640) if initial else H + self.R + self.rng.uniform(0, 120)
            clear = min((math.hypot(x - b["x"], y - b["y"]) for b in self.bubbles), default=999)
            if best is None or clear > best[0]:
                best = (clear, x, y)
            if clear > self.R * 2.5:
                break
        _, x, y = best
        # Everyone rises at nearly the same speed, so bubbles never catch
        # up with (and overlap) each other.
        self.bubbles.append({"word": word, "x": x, "y": y, "vy": self.rng.uniform(44, 50), "ph": self.rng.uniform(0, 6.3),
                             "popped": False, "pop_t": 0.0, "wob": 0.0, "color": self.rng.choice(RAINBOW)})

    def tick(self, dt: float) -> None:
        self.happy = max(0.0, self.happy - dt)
        self.target_pop = min(1.0, self.target_pop + dt * 3)
        for b in self.bubbles:
            if b["popped"]:
                b["pop_t"] += dt
            else:
                b["y"] -= b["vy"] * dt
                b["wob"] = max(0.0, b["wob"] - dt)
        alive = [b for b in self.bubbles if not (b["popped"] and b["pop_t"] > 0.25) and b["y"] > 70]
        removed = len(self.bubbles) - len(alive)
        self.bubbles = alive
        for _ in range(removed):
            self._spawn()
        while len([b for b in self.bubbles if not b["popped"]]) < 7:
            self._spawn()

    def click(self, x: float, y: float) -> None:
        for b in sorted(self.bubbles, key=lambda b: -b["y"]):
            if b["popped"]:
                continue
            bx = b["x"] + math.sin(self.t * 1.6 + b["ph"]) * 14
            if (x - bx) ** 2 + (y - b["y"]) ** 2 <= (self.R * 1.05) ** 2:
                if b["word"] == self.target:
                    b["popped"] = True
                    sound.play("pop")
                    self.burst(bx, b["y"], ["#ffffff", "#bfefff", b["color"]], 26, size=8)
                    if not self.missed:
                        self.score += 1
                    self.good(bx, b["y"], "Pop! +1" if not self.missed else "Pop!")
                    self.happy = 1.0
                    self.round += 1
                    if self.round >= self.ROUNDS:
                        self.finish(self.score, [f"{self.score} / {self.ROUNDS} popped first try"])
                        return
                    self.target = self.targets[self.round]
                    self.missed = False
                    self.target_pop = 0.0
                else:
                    b["wob"] = 0.5
                    self.missed = True
                    self.bad(bx, b["y"], f"That's '{b['word']}'")
                return

    def draw_game(self, p: QPainter) -> None:
        # Sea floor, weeds.
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f2d79b"))
        p.drawEllipse(QPointF(500, 760), 700, 130)
        for i, x in enumerate((40, 250, 620, 960)):
            p.setPen(QPen(QColor("#3fae6a"), 14, Qt.SolidLine, Qt.RoundCap))
            path = QPainterPath()
            path.moveTo(x, 690)
            for k in range(1, 6):
                path.lineTo(x + math.sin(self.t * 1.5 + k + i) * 16, 690 - k * 40)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        for b in self.bubbles:
            bx = b["x"] + math.sin(self.t * 1.6 + b["ph"]) * 14 + math.sin(self.t * 40) * 8 * b["wob"]
            if b["popped"]:
                k = b["pop_t"] / 0.25
                circle(p, bx, b["y"], self.R * (1 + k * 0.5), QColor(255, 255, 255, int(200 * (1 - k))), None)
                continue
            col = qc(b["color"])
            fill = QColor(col)
            fill.setAlpha(70)
            circle(p, bx, b["y"], self.R, fill, QColor(255, 255, 255, 230), 5)
            ellipse(p, bx - self.R * 0.4, b["y"] - self.R * 0.45, self.R * 0.2, self.R * 0.12, QColor(255, 255, 255, 220))
            text(p, b["word"], bx, b["y"], 26, WHITE, col.darker(160), 6, max_w=self.R * 1.75)

        # Finn and the speech bubble with the target word.
        fy = 470 + math.sin(self.t * 2) * 10
        draw_fish(p, 150, fy, 210, "#ff9f1c", 1, self.t, self.happy)
        k = ease_out_back(self.target_pop)
        p.save()
        p.translate(150, 290)
        p.scale(k, k)
        rounded(p, QRectF(-130, -80, 260, 150), 34, WHITE, INK, 5, shadow=6)
        tail = QPainterPath()
        tail.moveTo(-20, 68)
        tail.lineTo(10, 110)
        tail.lineTo(30, 68)
        p.setPen(Qt.NoPen)
        p.setBrush(WHITE)
        p.drawPath(tail)
        text(p, "Pop...", 0, -45, 18, "#1f6fb8")
        text(p, self.target, 0, 10, 52, INK, max_w=230)
        p.restore()


# ---------------------------------------------------------------------------
# 3. Memory Match
# ---------------------------------------------------------------------------

class MemoryMatch(GameCanvas):
    key_name = "memory"
    title = "Memory Match"
    backdrop = "candy"
    instructions = "Flip two cards to find a matching pair.\nSay the word out loud every time you flip!\nFewest moves wins the most stars."
    lower_is_better = True

    def start_game(self) -> None:
        n = len(self.words)
        self.star_thresholds = (n * 3, n * 2, round(n * 1.4))
        deck = self.words * 2
        self.rng.shuffle(deck)
        cols = n if n <= 6 else math.ceil(n * 2 / 3)
        rows = math.ceil(len(deck) / cols)
        gap = 18
        area = QRectF(30, 90, W - 60, H - 110)
        cw = min((area.width() - gap * (cols - 1)) / cols, ((area.height() - gap * (rows - 1)) / rows) * 0.8)
        ch = cw * 1.25
        total_w = cols * cw + gap * (cols - 1)
        total_h = rows * ch + gap * (rows - 1)
        x0 = area.center().x() - total_w / 2
        y0 = area.center().y() - total_h / 2
        self.cards = []
        for i, w in enumerate(deck):
            r, c = divmod(i, cols)
            self.cards.append({"word": w, "rect": QRectF(x0 + c * (cw + gap), y0 + r * (ch + gap), cw, ch),
                               "flip": 0.0, "up": False, "matched": False, "match_t": 0.0, "deal": i * 0.06})
        self.open: list[dict] = []
        self.moves = 0
        self.pairs = 0
        self.hide_at = None

    def hud_text(self) -> str:
        return f"Moves: {self.moves}"

    def tick(self, dt: float) -> None:
        for c in self.cards:
            target = 1.0 if c["up"] else 0.0
            c["flip"] += (target - c["flip"]) * min(1.0, dt * 12)
            if c["matched"]:
                c["match_t"] += dt
            c["deal"] = max(0.0, c["deal"] - dt)
        if self.hide_at is not None and self.t >= self.hide_at:
            for c in self.open:
                c["up"] = False
            self.open = []
            self.hide_at = None

    def click(self, x: float, y: float) -> None:
        if self.hide_at is not None:
            return
        for c in self.cards:
            if c["rect"].contains(x, y) and not c["up"] and not c["matched"]:
                c["up"] = True
                sound.play("flip")
                self.open.append(c)
                if len(self.open) == 2:
                    self.moves += 1
                    a, b = self.open
                    if a["word"] == b["word"]:
                        a["matched"] = b["matched"] = True
                        self.pairs += 1
                        self.open = []
                        cx = (a["rect"].center().x() + b["rect"].center().x()) / 2
                        cy = (a["rect"].center().y() + b["rect"].center().y()) / 2
                        self.good(cx, cy, "Match!")
                        for card in (a, b):
                            self.burst(card["rect"].center().x(), card["rect"].center().y(), RAINBOW, 14, shape="star")
                        if self.pairs == len(self.words):
                            self.finish(self.moves, [f"All {self.pairs} pairs in {self.moves} moves"])
                    else:
                        self.hide_at = self.t + 1.0
                return

    def draw_game(self, p: QPainter) -> None:
        for i, c in enumerate(self.cards):
            r = c["rect"]
            deal = ease_out_back(1 - min(1.0, c["deal"] / 0.06 / max(1, len(self.cards)) * 1.0)) if c["deal"] > 0 else 1.0
            if c["deal"] > 0:
                continue
            f = c["flip"]
            sx = abs(math.cos(math.pi * f))
            face = f > 0.5
            bounce = math.sin(min(1.0, c["match_t"] * 3) * math.pi) * 14 if c["matched"] else 0
            p.save()
            p.translate(r.center().x(), r.center().y() - bounce)
            p.scale(max(0.02, sx) * deal, deal)
            rr = QRectF(-r.width() / 2, -r.height() / 2, r.width(), r.height())
            if face:
                fill = "#d9ffe6" if c["matched"] else WHITE
                rounded(p, rr, 20, fill, GOOD if c["matched"] else INK, 5, shadow=6)
                text(p, c["word"], 0, 0, r.width() * 0.26, INK, max_w=r.width() - 22)
                if c["matched"]:
                    star(p, rr.right() - 22, rr.top() + 22, 14, GOLD, INK, 2)
            else:
                col = qc(RAINBOW[i % 7])
                rounded(p, rr, 20, col, INK, 5, shadow=6)
                rounded(p, rr.adjusted(10, 10, -10, -10), 14, col.lighter(125))
                star(p, 0, 0, r.width() * 0.22, WHITE, INK, 3, rot=-90 + 8 * math.sin(self.t * 2 + i))
            p.restore()


# ---------------------------------------------------------------------------
# 4. Peekaboo Owl (remember the word, say it, check)
# ---------------------------------------------------------------------------

class PeekabooOwl(GameCanvas):
    key_name = "peek"
    title = "Peekaboo Owl"
    backdrop = "forest"
    instructions = "Look at Hoot's sign... then Hoot hides it!\nSay the word you saw. Tap Peek! to check.\nGrown-up: did they get it right?"
    star_thresholds = (5, 8, 10)
    ROUNDS = 10

    def start_game(self) -> None:
        self.rounds = [self.words[i % len(self.words)] for i in range(self.ROUNDS)]
        self.rng.shuffle(self.rounds)
        self.r = 0
        self.score = 0
        self.results: list[bool] = []
        self._begin_round()

    def hud_text(self) -> str:
        return f"Word {min(self.r + 1, self.ROUNDS)} / {self.ROUNDS}"

    def _begin_round(self) -> None:
        self.phase = "show"
        self.phase_t = 0.0
        self.wings = 0.0  # 0 = open, 1 = covering the sign
        self.buttons = []

    def _peek(self) -> None:
        self.phase = "reveal"
        self.phase_t = 0.0
        sound.play("whoosh")
        self.buttons = [
            CanvasButton(QRectF(250, 590, 230, 74), "Got it!", "#2ec97a", lambda: self._answer(True), icon="✓", size=24),
            CanvasButton(QRectF(520, 590, 230, 74), "Not yet", "#ff8a5b", lambda: self._answer(False), icon="↺", size=22),
        ]

    def _answer(self, ok: bool) -> None:
        self.results.append(ok)
        if ok:
            self.score += 1
            self.good(500, 330, "Hoo-ray!")
        else:
            sound.play("click")
        self.r += 1
        if self.r >= self.ROUNDS:
            self.finish(self.score, [f"{self.score} / {self.ROUNDS} remembered"])
            return
        self._begin_round()

    def key(self, k: int) -> None:
        if self.phase == "hidden" and k in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._peek()
        elif self.phase == "reveal":
            if k in (Qt.Key_Right, Qt.Key_Y, Qt.Key_Return, Qt.Key_Enter):
                self._answer(True)
            elif k in (Qt.Key_Left, Qt.Key_N):
                self._answer(False)

    def tick(self, dt: float) -> None:
        self.phase_t += dt
        if self.phase == "show" and self.phase_t > 2.2:
            self.phase = "hidden"
            self.phase_t = 0.0
            sound.play("flip")
            self.buttons = [CanvasButton(QRectF(375, 590, 250, 78), "Peek!", "#9678e6", self._peek, icon="", size=26)]
        target = 1.0 if self.phase == "hidden" else 0.0
        self.wings += (target - self.wings) * min(1.0, dt * 9)

    def draw_game(self, p: QPainter) -> None:
        # Branch.
        rounded(p, QRectF(-40, 505, W + 80, 46), 23, "#8a5a35", INK, 5)
        for x in (120, 860):
            ellipse(p, x, 495, 60, 24, "#6cc46a", INK, 3)
        draw_owl(p, 500, 340, 300, eyes_closed=self.phase == "hidden", t=self.t)
        # The sign.
        sign = QRectF(500 - 220, 380, 440, 130)
        if self.phase == "show":
            k = ease_out_back(min(1.0, self.phase_t * 3))
        else:
            k = 1.0
        p.save()
        p.translate(500, 445)
        p.scale(k, k)
        p.translate(-500, -445)
        rounded(p, sign, 20, "#fff6d6", INK, 5, shadow=6)
        text(p, self.rounds[min(self.r, self.ROUNDS - 1)], 500, 445, 64, INK, max_w=410)
        p.restore()
        # Hoot's wings sweep in from the sides and cover the sign.
        k = ease_in_out(self.wings)
        for d in (-1, 1):
            wx = 500 + d * lerp(330, 112, k)
            p.save()
            p.translate(wx, 440)
            p.rotate(d * lerp(25, 0, k))
            ellipse(p, 0, 0, 125, 92, "#8f5f3b", INK, 5)
            for i in range(4):
                fx = -d * 70 + d * i * 34
                p.setPen(QPen(QColor("#6e4428"), 5, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(fx, -40), QPointF(fx + d * 18, 40))
            p.restore()
        if self.phase == "hidden":
            text(p, "Who-o-o was it? Say it!", 500, 125, 30, WHITE, INK, 7)
        elif self.phase == "reveal":
            text(p, "Did you get it?", 500, 125, 30, WHITE, INK, 7)
        else:
            text(p, "Look carefully...", 500, 125, 30, WHITE, INK, 7)
        # Results so far: a row of stars on the left.
        for i in range(self.ROUNDS):
            y = 120 + i * 50
            if i < len(self.results):
                star(p, 50, y, 20, GOLD if self.results[i] else QColor("#d8d8e4"), INK, 3)
            else:
                circle(p, 50, y, 8, QColor(255, 255, 255, 140))


# ---------------------------------------------------------------------------
# 5. Letter Train (build the word from balloon letters)
# ---------------------------------------------------------------------------

class LetterTrain(GameCanvas):
    key_name = "scramble"
    title = "Letter Train"
    backdrop = "meadow"
    instructions = "Pop the letter balloons in the right order\nto load the word onto the train.\nThen say the word and wave it goodbye!"
    star_thresholds = (8, 4, 1)
    lower_is_better = True

    def start_game(self) -> None:
        self.order = self.rng.sample(self.words, len(self.words))
        self.i = 0
        self.oops = 0
        self._setup_word(arriving=True)

    def hud_text(self) -> str:
        return f"Word {min(self.i + 1, len(self.order))} / {len(self.order)}"

    def _setup_word(self, arriving: bool) -> None:
        self.word = self.order[self.i]
        self.letters = list(self.word)
        self.pos = 0
        n = len(self.letters)
        self.car_w = min(110.0, 700.0 / max(1, n))
        self.train_len = n * (self.car_w + 8) + 150
        self.train_x = -self.train_len - 40 if arriving else 0.0
        self.train_target = (W - self.train_len) / 2
        self.phase = "arrive"
        self.loaded: list[dict] = []
        # Balloons, scattered without overlapping, in a jumbled order.
        letters = self.letters[:]
        for _ in range(20):
            self.rng.shuffle(letters)
            if "".join(letters) != self.word or n < 2:
                break
        r = 48 if n <= 7 else 40
        self.balloons = []
        cols = min(n, 6)
        rows = math.ceil(n / cols)
        for k, ch in enumerate(letters):
            row, col = divmod(k, cols)
            x = 130 + (W - 260) * (col + 0.5) / cols + self.rng.uniform(-25, 25)
            y = 150 + row * 150 + self.rng.uniform(-15, 25) + (60 if rows == 1 else 0)
            self.balloons.append({"ch": ch, "x": x, "y": y, "r": r, "color": RAINBOW[k % 7], "ph": self.rng.uniform(0, 6),
                                  "shake": 0.0, "fly": None})
        self.buttons = []

    def _car_center(self, k: int) -> tuple[float, float]:
        # Carriages run left to right in reading order, the engine is on
        # the right at the front.
        x = self.train_x + k * (self.car_w + 8) + self.car_w / 2
        return x, 560

    def click(self, x: float, y: float) -> None:
        if self.phase != "load":
            return
        for b in self.balloons:
            if b["fly"] is not None:
                continue
            bx = b["x"] + math.sin(self.t * 2 + b["ph"]) * 6
            by = b["y"] + math.sin(self.t * 1.7 + b["ph"]) * 8
            if (x - bx) ** 2 + (y - by) ** 2 <= (b["r"] * 1.15) ** 2:
                if b["ch"].lower() == self.letters[self.pos].lower():
                    sound.play("pop")
                    b["fly"] = {"t": 0.0, "from": (bx, by), "slot": self.pos}
                    self.pos += 1
                    self.burst(bx, by, [b["color"], "#ffffff"], 12, size=6)
                    if self.pos == len(self.letters):
                        self.phase = "say"
                        self.phase_t = 0.0
                else:
                    b["shake"] = 0.45
                    self.oops += 1
                    self.bad(bx, by, "Oops!")
                return

    def _go(self) -> None:
        self.phase = "leave"
        self.buttons = []
        sound.play("whoosh")

    def key(self, k: int) -> None:
        if self.phase == "say" and k in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Right):
            self._go()

    def tick(self, dt: float) -> None:
        for b in self.balloons:
            b["shake"] = max(0.0, b["shake"] - dt)
            if b["fly"] is not None:
                b["fly"]["t"] = min(1.0, b["fly"]["t"] + dt * 2.6)
        if self.phase == "arrive":
            self.train_x += (self.train_target - self.train_x) * min(1.0, dt * 4)
            if abs(self.train_x - self.train_target) < 2:
                self.train_x = self.train_target
                self.phase = "load"
        elif self.phase == "say":
            self.phase_t += dt
            if self.phase_t > 0.5 and not self.buttons:
                self.good(W / 2, 330, "Say it!")
                self.buttons = [CanvasButton(QRectF(W / 2 - 150, 380, 300, 80), "Choo choo!", "#ff6363", self._go,
                                             icon="", size=26)]
        elif self.phase == "leave":
            self.train_x += 650 * dt
            if self.rng.random() < 0.5:
                from .engine import Particle
                ex = self.train_x + self.train_len - 95
                self.particles.append(Particle(ex, 430, self.rng.uniform(-40, -10), self.rng.uniform(-90, -40), 1.0, 1.0,
                                               self.rng.uniform(12, 22), QColor(255, 255, 255, 200), "dot", 0, 0, -30))
            if self.train_x > W + 40:
                self.i += 1
                if self.i >= len(self.order):
                    self.finish(self.oops, [f"{len(self.order)} words built", f"{self.oops} oops taps"])
                    return
                self._setup_word(arriving=True)

    def draw_game(self, p: QPainter) -> None:
        # Hills and track.
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#9ad97a"))
        p.drawEllipse(QPointF(200, 700), 420, 170)
        p.setBrush(QColor("#85cf68"))
        p.drawEllipse(QPointF(820, 720), 460, 190)
        rounded(p, QRectF(-50, 618, W + 100, 14), 7, "#8a5a35")
        for x in range(-20, int(W) + 40, 46):
            rounded(p, QRectF(x, 626, 30, 18), 4, "#6e4428")

        # Train: carriages then engine at the front (right).
        n = len(self.letters)
        for k in range(n):
            cx, cy = self._car_center(k)
            r = QRectF(cx - self.car_w / 2, 520, self.car_w, 86)
            rounded(p, r, 12, RAINBOW[k % 7], INK, 4)
            rounded(p, r.adjusted(8, 8, -8, -30), 8, WHITE, INK, 2)
            if k >= self.pos:
                # A faint 'ghost' letter shows what goes here.
                text(p, self.letters[k], cx, 548, min(40, self.car_w * 0.5), QColor(45, 40, 64, 55), max_w=self.car_w - 18)
            for wx in (r.left() + self.car_w * 0.25, r.right() - self.car_w * 0.25):
                circle(p, wx, 612, 13, "#2d2840")
                circle(p, wx, 612, 5, "#ffcc33")
            if k < n - 1:
                rounded(p, QRectF(r.right(), 585, 8, 8), 3, INK)
        engine_x = self.train_x + n * (self.car_w + 8)
        draw_train_engine(p, engine_x, 625, 150, self.t, self.phase in ("arrive", "leave"))

        # Letters that have arrived in their carriages.
        for b in self.balloons:
            if b["fly"] is None:
                continue
            slot = b["fly"]["slot"]
            sx, sy = self._car_center(slot)
            sy = 548
            k = ease_out_cubic(b["fly"]["t"])
            fx, fy = b["fly"]["from"]
            x = lerp(fx, sx, k)
            y = lerp(fy, sy, k) - math.sin(k * math.pi) * 60
            if k < 1:
                draw_balloon(p, x, y, b["r"] * (1 - 0.55 * k), b["color"], b["ch"], self.t, b["ph"])
            else:
                text(p, b["ch"], sx, sy, min(40, self.car_w * 0.5), INK, max_w=self.car_w - 18)

        for b in self.balloons:
            if b["fly"] is not None:
                continue
            bx = b["x"] + math.sin(self.t * 2 + b["ph"]) * 6 + math.sin(self.t * 50) * 10 * b["shake"]
            by = b["y"] + math.sin(self.t * 1.7 + b["ph"]) * 8
            draw_balloon(p, bx, by, b["r"], b["color"], b["ch"], self.t, b["ph"])

        if self.phase in ("say", "leave"):
            text(p, self.word, W / 2, 230, 84, "#ffcc33", INK, 10, max_w=800)


# ---------------------------------------------------------------------------
# 6. Whack-a-Word (new)
# ---------------------------------------------------------------------------

class WhackAWord(GameCanvas):
    key_name = "whack"
    title = "Whack-a-Word"
    backdrop = "meadow"
    instructions = "The moles are holding up words!\nBonk only the moles with the word at the top.\nSay it as you bonk! 45 seconds."
    star_thresholds = (5, 10, 16)
    HOLES = [(230, 395), (500, 395), (770, 395), (230, 605), (500, 605), (770, 605)]

    def start_game(self) -> None:
        self.hits = 0
        self.misses = 0
        self.target = self.rng.choice(self.words)
        self.target_pop = 0.0
        self.moles = [None] * len(self.HOLES)
        self.spawn_in = 0.3
        self.start_timer(45)

    def hud_text(self) -> str:
        return f"Bonks: {self.hits}"

    def _new_target(self) -> None:
        others = _other_words(self.words, self.target)
        self.target = self.rng.choice(others)
        self.target_pop = 0.0
        sound.play("go")

    def tick(self, dt: float) -> None:
        self.target_pop = min(1.0, self.target_pop + dt * 3)
        self.spawn_in -= dt
        up_time = max(1.25, 2.1 - self.hits * 0.04)
        for i, m in enumerate(self.moles):
            if m is None:
                continue
            m["t"] += dt
            if m["bonked"] is not None:
                m["bonked"] += dt
                if m["bonked"] > 0.45:
                    self.moles[i] = None
            elif m["t"] > up_time:
                self.moles[i] = None
        if self.spawn_in <= 0:
            free = [i for i, m in enumerate(self.moles) if m is None]
            if free:
                i = self.rng.choice(free)
                showing_target = any(m and m["word"] == self.target and m["bonked"] is None for m in self.moles)
                p_target = 0.35 if showing_target else 0.6
                word = self.target if self.rng.random() < p_target else self.rng.choice(_other_words(self.words, self.target))
                self.moles[i] = {"word": word, "t": 0.0, "bonked": None, "up": up_time}
            self.spawn_in = self.rng.uniform(0.45, 0.85)
        if self.timer_left <= 0:
            self.finish(self.hits, [f"{self.hits} right words bonked", f"{self.misses} oops bonks"])

    def _height(self, m) -> float:
        """How far up the mole is, 0..1."""
        if m["bonked"] is not None:
            return max(0.0, 1 - m["bonked"] / 0.45)
        t, up = m["t"], m["up"]
        if t < 0.18:
            return ease_out_back(t / 0.18)
        if t > up - 0.18:
            return max(0.0, (up - t) / 0.18)
        return 1.0

    def click(self, x: float, y: float) -> None:
        for i, m in enumerate(self.moles):
            if m is None or m["bonked"] is not None:
                continue
            hx, hy = self.HOLES[i]
            h = self._height(m)
            if h < 0.4:
                continue
            top = hy + 95 - 165 * h - 90
            if hx - 105 <= x <= hx + 105 and top - 10 <= y <= hy + 20:
                m["bonked"] = 0.0
                if m["word"] == self.target:
                    self.hits += 1
                    self.good(hx, top, "Bonk! +1")
                    if self.hits % 4 == 0 and len(self.words) > 1:
                        self._new_target()
                else:
                    self.misses += 1
                    self.bad(hx, top, f"That's '{m['word']}'")
                return

    def draw_game(self, p: QPainter) -> None:
        k = ease_out_back(self.target_pop)
        # Grass field, then the target banner over it.
        rounded(p, QRectF(-60, 250, W + 120, 520), 60, "#8fd16d")
        for i in range(14):
            x = (i * 83) % 1000
            p.setPen(QPen(QColor("#6dbb4f"), 4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x, 290 + (i % 3) * 120), QPointF(x + 8, 274 + (i % 3) * 120))
        p.save()
        p.translate(W / 2, 128)
        p.scale(k, k)
        rounded(p, QRectF(-260, -48, 520, 96), 30, "#fff6d6", INK, 5, shadow=6)
        text(p, "Bonk:", -170, 0, 26, "#ff6363", INK, 4)
        text(p, self.target, 60, 0, 52, INK, max_w=320)
        p.restore()
        for i, (hx, hy) in enumerate(self.HOLES):
            ellipse(p, hx, hy, 105, 34, "#4a2e1f", INK, 4)
            m = self.moles[i]
            if m is not None:
                h = self._height(m)
                p.save()
                p.setClipRect(QRectF(hx - 160, hy - 400, 320, 410))
                my = hy + 95 - 165 * h
                squish = min(1.0, (m["bonked"] or 0) * 4) if m["bonked"] is not None else 0
                draw_mole(p, hx, my, 170, squish, self.t)
                # The mole holds its word sign up in front of its tummy.
                sy = my + 38
                for d in (-1, 1):
                    circle(p, hx + d * 88, sy, 16, "#9c6b4e", INK, 3)
                rounded(p, QRectF(hx - 84, sy - 30, 168, 60), 14, WHITE, INK, 4)
                text(p, m["word"], hx, sy, 28, INK, max_w=150)
                p.restore()
            # Front lip of the hole, over the mole's bottom.
            p.setPen(QPen(INK, 4))
            p.setBrush(QColor("#7a4f35"))
            p.drawChord(QRectF(hx - 112, hy - 30, 224, 76), 180 * 16, 180 * 16)


# ---------------------------------------------------------------------------
# 7. Word Catcher (new)
# ---------------------------------------------------------------------------

class WordCatcher(GameCanvas):
    key_name = "catch"
    title = "Word Catcher"
    backdrop = "sky"
    instructions = "Move the basket with the mouse (or ← →).\nCatch only the apples with the word at the top!\nSay it when you catch it. 45 seconds."
    star_thresholds = (5, 10, 15)
    BASKET_Y = 610
    BASKET_W = 170

    def start_game(self) -> None:
        self.caught = 0
        self.oops = 0
        self.bx = W / 2
        self.aim = W / 2
        self.tilt = 0.0
        self.items: list[dict] = []
        self.spawn_in = 0.2
        self.target = self.rng.choice(self.words)
        self.target_pop = 0.0
        self.keys = 0
        self.start_timer(45)

    def hud_text(self) -> str:
        return f"Caught: {self.caught}"

    def hover_move(self, x: float, y: float) -> None:
        self.aim = max(self.BASKET_W / 2, min(W - self.BASKET_W / 2, x))

    def click(self, x: float, y: float) -> None:
        self.hover_move(x, y)

    def key(self, k: int) -> None:
        if k == Qt.Key_Left:
            self.aim = max(self.BASKET_W / 2, self.aim - 90)
        elif k == Qt.Key_Right:
            self.aim = min(W - self.BASKET_W / 2, self.aim + 90)

    def tick(self, dt: float) -> None:
        self.target_pop = min(1.0, self.target_pop + dt * 3)
        prev = self.bx
        self.bx += (self.aim - self.bx) * min(1.0, dt * 12)
        self.tilt += ((self.bx - prev) / max(dt, 1e-3) * 0.02 - self.tilt) * min(1.0, dt * 10)
        self.spawn_in -= dt
        if self.spawn_in <= 0:
            showing = sum(1 for it in self.items if it["word"] == self.target)
            word = self.target if (showing == 0 or self.rng.random() < 0.4) else self.rng.choice(_other_words(self.words, self.target))
            self.items.append({"word": word, "x": self.rng.uniform(80, W - 80), "y": 190.0, "age": 0.0,
                               "vy": self.rng.uniform(110, 160) + self.caught * 3, "color": self.rng.choice(["#ff5d5d", "#ffb02e", "#8bd346", "#ff7ab8"]),
                               "spin": self.rng.uniform(-1, 1)})
            self.spawn_in = self.rng.uniform(0.75, 1.15)
        keep = []
        for it in self.items:
            it["age"] += dt
            it["y"] += it["vy"] * dt * min(1.0, it["age"] * 2)
            in_basket = abs(it["x"] - self.bx) < self.BASKET_W / 2 + 10 and self.BASKET_Y - 50 < it["y"] < self.BASKET_Y + 5
            if in_basket:
                if it["word"] == self.target:
                    self.caught += 1
                    self.good(it["x"], it["y"] - 40, "Yum! +1")
                    if self.caught % 5 == 0 and len(self.words) > 1:
                        self.target = self.rng.choice(_other_words(self.words, self.target))
                        self.target_pop = 0.0
                        sound.play("go")
                else:
                    self.oops += 1
                    self.bad(it["x"], it["y"] - 40, f"That's '{it['word']}'")
                continue
            if it["y"] > H + 60:
                continue
            keep.append(it)
        self.items = keep
        if self.timer_left <= 0:
            self.finish(self.caught, [f"{self.caught} right apples caught", f"{self.oops} oops catches"])

    def draw_game(self, p: QPainter) -> None:
        # Tree canopy along the top, grass along the bottom.
        for i, x in enumerate(range(-40, int(W) + 80, 120)):
            circle(p, x, 70 + (i % 2) * 18, 95, "#5fbf4a" if i % 2 else "#4fae3d")
        rounded(p, QRectF(-60, 640, W + 120, 120), 40, "#7cc95c")
        for it in self.items:
            g = ease_out_back(min(1.0, it["age"] * 3))
            p.save()
            p.translate(it["x"], it["y"])
            p.scale(g, g)
            draw_apple(p, 0, 0, 36, it["color"])
            rounded(p, QRectF(-70, 36, 140, 46), 14, WHITE, INK, 3)
            text(p, it["word"], 0, 59, 24, INK, max_w=128)
            p.restore()
        k = ease_out_back(self.target_pop)
        p.save()
        p.translate(W / 2, 118)
        p.scale(k, k)
        rounded(p, QRectF(-240, -44, 480, 88), 30, WHITE, INK, 5, shadow=6)
        text(p, "Catch:", -150, 0, 26, "#ff6363", INK, 4)
        text(p, self.target, 70, 0, 50, INK, max_w=300)
        p.restore()
        draw_basket(p, self.bx, self.BASKET_Y + 20, self.BASKET_W, max(-12, min(12, self.tilt)))


GAME_CLASSES: dict[str, type[GameCanvas]] = {
    cls.key_name: cls for cls in (RocketBlitz, BubblePop, MemoryMatch, PeekabooOwl, LetterTrain, WhackAWord, WordCatcher)
}
