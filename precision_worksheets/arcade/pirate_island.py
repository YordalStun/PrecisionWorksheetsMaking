"""Pirate Island: a 3D Monopoly-style board game, drawn in perspective with plain QPainter."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
    QTransform,
)

from . import sound
from .engine import (
    GOLD,
    INK,
    W,
    WHITE,
    CanvasButton,
    GameCanvas,
    circle,
    ease_in_out,
    ease_out_back,
    ease_out_cubic,
    ellipse,
    fit_size,
    font,
    lerp,
    qc,
    rounded,
    star,
    text,
)

# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

SIDE = 7
N_SQUARES = 4 * (SIDE - 1)
START, TREASURE, CANNON, QUICKSAND = 0, 6, 12, 18
CANNON_JUMP = 4
QUICKSAND_SLIDE = 3
TREASURE_COINS = 2
FULL_SET_BONUS = 2
MAX_LEVEL = 3
ROUNDS_FOR_PLAYERS = {1: 12, 2: 8, 3: 6, 4: 5}
GROUP_COLORS = ["#ff6b6b", "#4cc3f0", "#7bd88f", "#ffd43b", "#b388ff", "#ffa94d", "#2ec4b6", "#ff8cc6"]
PLAYER_COLORS = ["#ff4d4d", "#3b82f6", "#22c55e", "#fbbf24"]
CORNER_KINDS = {START: "start", TREASURE: "treasure", CANNON: "cannon", QUICKSAND: "quicksand"}


@dataclass
class Square:
    index: int
    kind: str  # start | word | map | treasure | cannon | quicksand
    word: str = ""
    group: int = -1
    owner: int | None = None
    level: int = 0


@dataclass
class Player:
    name: str
    color: str
    pos: int = START
    coins: int = 0
    words_read: int = 0


@dataclass(frozen=True)
class MapCard:
    kind: str  # challenge | coins | again | home
    text: str
    coins: int = 0


MAP_CARDS = (
    MapCard("challenge", "Spell this word out loud!", 2),
    MapCard("challenge", "Read it 3 times super fast!", 2),
    MapCard("challenge", "Say a sentence with this word!", 2),
    MapCard("challenge", "Find this word on the island!", 2),
    MapCard("coins", "You dug up buried gold!", 2),
    MapCard("coins", "A parrot brings you a shiny coin!", 1),
    MapCard("again", "A fair wind! Roll again."),
    MapCard("home", "Sail home to SET SAIL!", 1),
)


def is_word_square(i: int) -> bool:
    return i % (SIDE - 1) not in (0, 3)


def build_squares(words: list[str], rng: random.Random) -> list[Square]:
    words = [w for w in words if w.strip()] or ["?"]
    slots = [i for i in range(N_SQUARES) if is_word_square(i)]
    dealt = iter(_deal_words(words, len(slots), rng))
    squares = []
    for i in range(N_SQUARES):
        side, pos = divmod(i, SIDE - 1)
        if i in CORNER_KINDS:
            squares.append(Square(i, CORNER_KINDS[i]))
        elif pos == 3:
            squares.append(Square(i, "map"))
        else:
            squares.append(Square(i, "word", next(dealt), side * 2 + (0 if pos < 3 else 1)))
    return squares


def _deal_words(words: list[str], n: int, rng: random.Random) -> list[str]:
    # Each word equally often, and the two squares of a colour set show different words.
    dealt = [words[i % len(words)] for i in range(n)]
    if len(set(words)) < 2:
        return dealt
    for _ in range(200):
        rng.shuffle(dealt)
        if all(dealt[k] != dealt[k + 1] for k in range(0, n - 1, 2)):
            return dealt
    return [words[i % len(words)] for i in range(n)]


class IslandGame:
    """The rules only - the canvas calls these one step at a time so it can animate each."""

    def __init__(self, words: list[str], n_players: int, names: list[str] | None = None,
                 rng: random.Random | None = None, squares: list[Square] | None = None):
        self.rng = rng or random.Random()
        self.words = [w for w in words if w.strip()] or ["?"]
        self.squares = squares if squares is not None else build_squares(self.words, self.rng)
        n = max(1, min(4, n_players))
        names = list(names or [])
        self.players = [
            Player(names[i] if i < len(names) and names[i] else f"Player {i + 1}", PLAYER_COLORS[i])
            for i in range(n)
        ]
        self.rounds = ROUNDS_FOR_PLAYERS[n]
        self.total_turns = self.rounds * n
        self.turns_taken = 0
        self.current = 0
        self.full_sets: set[tuple[int, int]] = set()
        self._deck: list[MapCard] = []

    @property
    def player(self) -> Player:
        return self.players[self.current]

    @property
    def round_number(self) -> int:
        return min(self.rounds, self.turns_taken // len(self.players) + 1)

    @property
    def done(self) -> bool:
        return self.turns_taken >= self.total_turns

    def square_here(self) -> Square:
        return self.squares[self.player.pos]

    def roll(self) -> int:
        return self.rng.randint(1, 6)

    def step(self, direction: int = 1) -> int:
        """Move one square; sailing forward onto/past SET SAIL earns a coin (returned)."""
        p = self.player
        p.pos = (p.pos + direction) % N_SQUARES
        if direction > 0 and p.pos == START:
            p.coins += 1
            return 1
        return 0

    def answer_word(self, ok: bool) -> dict:
        sq = self.square_here()
        p = self.player
        out = {"coins": 0, "built": 0, "rent_to": None, "full_set": False}
        if not ok:
            return out
        p.coins += 1
        p.words_read += 1
        out["coins"] = 1
        if sq.owner is None:
            sq.owner, sq.level = self.current, 1
            out["built"] = 1
        elif sq.owner == self.current:
            if sq.level < MAX_LEVEL:
                sq.level += 1
                out["built"] = sq.level
        else:
            self.players[sq.owner].coins += 1
            out["rent_to"] = sq.owner
        key = (self.current, sq.group)
        if sq.owner == self.current and key not in self.full_sets:
            if all(s.owner == self.current for s in self.squares if s.group == sq.group):
                self.full_sets.add(key)
                p.coins += FULL_SET_BONUS
                out["full_set"] = True
        return out

    def draw_card(self) -> tuple[MapCard, str]:
        if not self._deck:
            self._deck = list(MAP_CARDS)
            self.rng.shuffle(self._deck)
        return self._deck.pop(), self.rng.choice(self.words)

    def resolve_card(self, card: MapCard, ok: bool = True) -> int:
        p = self.player
        earned = 0
        if card.kind == "challenge":
            earned = card.coins if ok else 0
        elif card.kind in ("coins", "home"):
            earned = card.coins
        if card.kind == "home":
            p.pos = START
        p.coins += earned
        return earned

    def treasure(self) -> int:
        self.player.coins += TREASURE_COINS
        return TREASURE_COINS

    def huts(self, player_index: int) -> int:
        return sum(s.level for s in self.squares if s.owner == player_index)

    def end_turn(self, extra: bool = False) -> None:
        if extra:
            return
        self.turns_taken += 1
        self.current = (self.current + 1) % len(self.players)

    def winners(self) -> list[int]:
        best = max(p.coins for p in self.players)
        return [i for i, p in enumerate(self.players) if p.coins == best]


# ---------------------------------------------------------------------------
# Board geometry: a 780 x 780 "texture" laid flat on the island, 100 units = 1 world unit
# ---------------------------------------------------------------------------

TEX = 780.0
CORNER = 140.0
CELL = 100.0
BAND = 26.0
HALF = TEX / 200.0
SEA_Y = -0.5
_CORNER_XY = {0: (640.0, 640.0), 1: (0.0, 640.0), 2: (0.0, 0.0), 3: (640.0, 0.0)}


def square_rect(i: int) -> QRectF:
    side, pos = divmod(i, SIDE - 1)
    if pos == 0:
        x, y = _CORNER_XY[side]
        return QRectF(x, y, CORNER, CORNER)
    if side == 0:
        return QRectF(640 - CELL * pos, 640, CELL, CORNER)
    if side == 1:
        return QRectF(0, 640 - CELL * pos, CORNER, CELL)
    if side == 2:
        return QRectF(140 + CELL * (pos - 1), 0, CELL, CORNER)
    return QRectF(640, 140 + CELL * (pos - 1), CORNER, CELL)


def band_rect(i: int) -> QRectF:
    """Colour stripe: along the far edge on the top/bottom rows, the inner edge on the side columns
    (so huts standing on it never hide a word from the camera)."""
    r = square_rect(i).adjusted(9, 9, -9, -9)
    side = i // (SIDE - 1)
    if side in (0, 2):
        return QRectF(r.x(), r.y(), r.width(), BAND - 4)
    if side == 1:
        return QRectF(r.right() - BAND + 4, r.y(), BAND - 4, r.height())
    return QRectF(r.x(), r.y(), BAND - 4, r.height())


def word_area(i: int) -> QRectF:
    r = square_rect(i).adjusted(6, 6, -6, -6)
    side = i // (SIDE - 1)
    if side in (0, 2):
        return r.adjusted(0, BAND, 0, 0)
    if side == 1:
        return r.adjusted(0, 0, -BAND, 0)
    return r.adjusted(BAND, 0, 0, 0)


def tex_to_world(tx: float, ty: float) -> tuple[float, float]:
    return tx / 100.0 - HALF, ty / 100.0 - HALF


def pawn_spot(i: int, slot: int = 0, crowd: int = 1) -> tuple[float, float]:
    r = square_rect(i)
    x, z = tex_to_world(r.center().x(), r.center().y())
    side, pos = divmod(i, SIDE - 1)
    if pos and side in (0, 2):
        z += 0.2
    if crowd > 1:
        dx, dz = ((-0.18, -0.13), (0.18, -0.13), (-0.18, 0.2), (0.18, 0.2))[slot % 4]
        x, z = x + dx, z + dz
    return x, z


def hut_spots(i: int, count: int) -> list[tuple[float, float]]:
    b = band_rect(i)
    x, z = tex_to_world(b.center().x(), b.center().y())
    if count == 1:
        return [(x, z)]
    if i // (SIDE - 1) in (0, 2):
        return [(x - 0.22, z), (x + 0.22, z)]
    return [(x, z - 0.22), (x, z + 0.22)]


# ---------------------------------------------------------------------------
# A tiny 3D camera and some vector helpers
# ---------------------------------------------------------------------------

FOCAL = 980.0
SCREEN_CENTRE = (612.0, 374.0)
CAM_PITCH = 0.9
CAM_DIST = 13.3
PAWN_SCALE = 1.3
TEX_SCALE = 1.6


def _normalize(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


LIGHT = _normalize((-0.45, 1.0, 0.55))


class Camera:
    def __init__(self, target, dist: float, pitch: float, yaw: float, focal: float = FOCAL,
                 centre: tuple[float, float] = SCREEN_CENTRE):
        tx, ty, tz = target
        cp, sp = math.cos(pitch), math.sin(pitch)
        self.ex = tx + dist * cp * math.sin(yaw)
        self.ey = ty + dist * sp
        self.ez = tz + dist * cp * math.cos(yaw)
        self.fx, self.fy, self.fz = _normalize((tx - self.ex, ty - self.ey, tz - self.ez))
        rx, rz = -self.fz, self.fx
        rn = math.hypot(rx, rz) or 1.0
        self.rx, self.rz = rx / rn, rz / rn
        self.ux = -self.rz * self.fy
        self.uy = self.rz * self.fx - self.rx * self.fz
        self.uz = self.rx * self.fy
        self.focal = focal
        self.cx, self.cy = centre

    def project(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        vx, vy, vz = x - self.ex, y - self.ey, z - self.ez
        d = max(0.1, vx * self.fx + vy * self.fy + vz * self.fz)
        k = self.focal / d
        return (self.cx + (vx * self.rx + vz * self.rz) * k,
                self.cy - (vx * self.ux + vy * self.uy + vz * self.uz) * k, d)

    def pt(self, x: float, y: float, z: float) -> QPointF:
        sx, sy, _ = self.project(x, y, z)
        return QPointF(sx, sy)

    def faces_camera(self, n, at) -> bool:
        return n[0] * (self.ex - at[0]) + n[1] * (self.ey - at[1]) + n[2] * (self.ez - at[2]) > 0

    @property
    def flatten(self) -> float:
        """How squashed a flat circle on the ground looks from here (1 = seen from straight above)."""
        return max(0.3, -self.fy)


def rot_x(a: float):
    c, s = math.cos(a), math.sin(a)
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def rot_y(a: float):
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def rot_z(a: float):
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def axis_angle(axis, a: float):
    x, y, z = _normalize(axis)
    c, s = math.cos(a), math.sin(a)
    t = 1 - c
    return ((t * x * x + c, t * x * y - s * z, t * x * z + s * y),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c))


def mat_mul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mat_vec(m, v):
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

# name: (outward normal, corners as top-left, top-right, bottom-right, bottom-left seen from outside)
BOX_FACES = (
    ("top", (0, 1, 0), ((-1, 1, -1), (1, 1, -1), (1, 1, 1), (-1, 1, 1))),
    ("bottom", (0, -1, 0), ((-1, -1, 1), (1, -1, 1), (1, -1, -1), (-1, -1, -1))),
    ("front", (0, 0, 1), ((-1, 1, 1), (1, 1, 1), (1, -1, 1), (-1, -1, 1))),
    ("back", (0, 0, -1), ((1, 1, -1), (-1, 1, -1), (-1, -1, -1), (1, -1, -1))),
    ("right", (1, 0, 0), ((1, 1, 1), (1, 1, -1), (1, -1, -1), (1, -1, 1))),
    ("left", (-1, 0, 0), ((-1, 1, -1), (-1, 1, 1), (-1, -1, 1), (-1, -1, -1))),
)
DIE_VALUES = {"top": 1, "bottom": 6, "right": 2, "left": 5, "front": 3, "back": 4}
# Rotation that brings each value's face to the top.
DIE_TOP = {1: IDENTITY, 6: rot_x(math.pi), 2: rot_z(math.pi / 2), 5: rot_z(-math.pi / 2),
           3: rot_x(-math.pi / 2), 4: rot_x(math.pi / 2)}
DIE_HALF = 0.3
PIPS = {
    1: ((50, 50),),
    2: ((27, 27), (73, 73)),
    3: ((25, 25), (50, 50), (75, 75)),
    4: ((28, 28), (72, 28), (28, 72), (72, 72)),
    5: ((27, 27), (73, 27), (50, 50), (27, 73), (73, 73)),
    6: ((28, 24), (72, 24), (28, 50), (72, 50), (28, 76), (72, 76)),
}
_UNIT = QPolygonF([QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)])
_TEX_QUAD = QPolygonF([QPointF(0, 0), QPointF(TEX, 0), QPointF(TEX, TEX), QPointF(0, TEX)])


def die_face_up(rot) -> int:
    best, value = -2.0, 1
    for name, n, _corners in BOX_FACES:
        up = mat_vec(rot, n)[1]
        if up > best:
            best, value = up, DIE_VALUES[name]
    return value


def shade(c, n) -> QColor:
    c = qc(c)
    d = max(0.0, n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2])
    k = 0.58 + 0.5 * d
    return QColor(min(255, int(c.red() * k)), min(255, int(c.green() * k)), min(255, int(c.blue() * k)), c.alpha())


def poly(p: QPainter, pts, fill, outline=INK, width: float = 2.0) -> None:
    p.setPen(QPen(qc(outline), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin) if outline is not None else Qt.NoPen)
    p.setBrush(qc(fill) if not isinstance(fill, (QLinearGradient, QRadialGradient)) else fill)
    p.drawPolygon(QPolygonF(pts))


def _newell(pts):
    nx = ny = nz = 0.0
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return _normalize((nx, ny, nz))


def draw_mesh(p: QPainter, cam: Camera, faces, centre, width: float = 1.8) -> None:
    """Draws a convex-ish solid: faces = [(world points, colour)], culled to those facing the camera."""
    for pts, color in faces:
        n = _newell(pts)
        fc = (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts), sum(q[2] for q in pts) / len(pts))
        if n[0] * (fc[0] - centre[0]) + n[1] * (fc[1] - centre[1]) + n[2] * (fc[2] - centre[2]) < 0:
            n = (-n[0], -n[1], -n[2])
        if cam.faces_camera(n, fc):
            poly(p, [cam.pt(*q) for q in pts], shade(color, n), INK, width)


def draw_box(p: QPainter, cam: Camera, centre, half, rot, colors, texture=None, width: float = 2.0) -> None:
    """A box at `centre` with half-sizes `half`, rotated by `rot`; `texture(name, painter)` may paint
    each visible face in a 0..100 square."""
    cx, cy, cz = centre
    hx, hy, hz = half
    for name, n_local, corners in BOX_FACES:
        n = mat_vec(rot, n_local)
        off = mat_vec(rot, (n_local[0] * hx, n_local[1] * hy, n_local[2] * hz))
        if not cam.faces_camera(n, (cx + off[0], cy + off[1], cz + off[2])):
            continue
        quad = []
        for c in corners:
            w = mat_vec(rot, (c[0] * hx, c[1] * hy, c[2] * hz))
            quad.append(cam.pt(cx + w[0], cy + w[1], cz + w[2]))
        color = colors.get(name, colors.get("*", WHITE)) if isinstance(colors, dict) else colors
        poly(p, quad, shade(color, n), INK, width)
        if texture is not None:
            t = QTransform.quadToQuad(_UNIT, QPolygonF(quad))
            if t is not None:
                p.save()
                p.setWorldTransform(t, True)
                texture(name, p)
                p.restore()


# ---------------------------------------------------------------------------
# The game
# ---------------------------------------------------------------------------

SAND = QColor("#f7dda4")
CHEST_POS = (1.35, -0.72)
DECK_POS = (-1.15, 1.72)
PALMS = ((-2.12, 0.78, 1.05, 0.25), (0.32, 0.22, 0.95, -0.2))  # x, z, height, lean
HOP_T = 0.3
ROLL_T = 1.25


class PirateIsland(GameCanvas):
    key_name = "pirate"
    title = "Pirate Island"
    backdrop = "sea"
    instructions = ("Roll the die and sail around the island.\nLand on a word? Read it out loud to build a hut!\n"
                    "The most gold coins at the end wins.")
    star_thresholds = (7, 12, 17)
    player_name = ""

    # -- setup ------------------------------------------------------------
    def start_game(self) -> None:
        self.squares = build_squares(self.words, self.rng)
        self.game: IslandGame | None = None
        self.phase = "setup"
        self.phase_t = 0.0
        self.wait = 0.0
        self.next_step = None
        self.banner = ("", 0.0, INK)
        self.moving: dict | None = None
        self.flying: dict | None = None
        self.card: tuple[MapCard, str] | None = None
        self.word_square: Square | None = None
        self.extra_turn = False
        self.highlight: int | None = None
        self.built_at: dict[int, float] = {}
        self.coin_shown: list[float] = []
        self.roll_value = 0
        self.die_anim: dict | None = None
        self.die_pos = (1.35, DIE_HALF, 1.35)
        self.die_rot = mat_mul(rot_y(0.5), DIE_TOP[self.rng.randint(1, 6)])
        self.chest_glow = -10.0
        self._bg: QPixmap | None = None
        self._bg_key = None
        self.buttons = []
        self._paths: dict = {}
        self._board_img: QImage | None = None
        self._make_static_art()

    def _make_static_art(self) -> None:
        rng = random.Random(7)
        self._speckles = QPainterPath()
        for _ in range(170):
            x, y = rng.uniform(4, TEX - 4), rng.uniform(4, TEX - 4)
            r = rng.uniform(1.2, 2.8)
            self._speckles.addEllipse(QPointF(x, y), r, r * 0.8)
        self._lagoon_outer = _blob(285, 392, 122, 100, rng, 11)
        self._lagoon_inner = _blob(288, 395, 96, 76, random.Random(3), 11)
        self._trail = QPainterPath(QPointF(392, 380))
        self._trail.cubicTo(QPointF(430, 330), QPointF(470, 390), QPointF(505, 352))
        wrng = random.Random(11)
        self._waves = []
        for gx in range(-7, 8):
            for gz in range(-7, 8):
                x, z = gx * 2.0 + wrng.uniform(-0.7, 0.7), gz * 2.0 + wrng.uniform(-0.7, 0.7)
                if max(abs(x), abs(z)) > 5.0:
                    self._waves.append((x, z, wrng.uniform(0, 6.28), wrng.uniform(0.7, 1.3)))

    def _setup(self, n: int) -> None:
        if self.phase != "setup":
            return
        names = [self.player_name or "Player 1"] + [f"Player {i + 1}" for i in range(1, n)]
        self.game = IslandGame(self.words, n, names, self.rng, squares=self.squares)
        r = self.game.rounds
        self.star_thresholds = (max(1, round(r * 0.6)), max(2, round(r * 1.0)), max(3, round(r * 1.4)))
        self.coin_shown = [0.0] * n
        sound.play("go")
        self._begin_turn()

    def hud_text(self) -> str:
        if self.game is None:
            return ""
        return f"Round {self.game.round_number} / {self.game.rounds}"

    # -- turn flow ----------------------------------------------------------
    def _say(self, msg: str, color=INK) -> None:
        self.banner = (msg, self.t, qc(color))

    def _begin_turn(self) -> None:
        self.phase = "await_roll"
        self.phase_t = 0.0
        pl = self.game.player
        self._say(f"{pl.name}'s turn - roll the die!" if len(self.game.players) > 1 else "Roll the die!", pl.color)
        self.buttons = [CanvasButton(QRectF(14, 592, 200, 74), "Roll!", "#ff7a1a", self._roll, size=28)]

    def _roll(self) -> None:
        if self.phase != "await_roll":
            return
        self.buttons = []
        self.roll_value = self.game.roll()
        yaw = self.rng.uniform(0, 2 * math.pi)
        self.die_anim = {
            "from": (4.3 + self.rng.uniform(-0.3, 0.3), 2.3, 3.0 + self.rng.uniform(-0.4, 0.4)),
            "to": (self.rng.uniform(0.55, 2.05), self.rng.uniform(0.75, 2.1)),
            "axis": _normalize((self.rng.uniform(-1, 1), self.rng.uniform(-1, 1), self.rng.uniform(-1, 1))),
            "spin": self.rng.uniform(3.5, 5.0) * math.pi,
            "final": mat_mul(rot_y(yaw), DIE_TOP[self.roll_value]),
            "bounces": 0,
        }
        self.phase = "rolling"
        self.phase_t = 0.0
        sound.play("whoosh")

    def _move(self, direction: int, steps: int, hop_t: float, then, hop_h: float = 0.55) -> None:
        self.phase = "moving"
        self.phase_t = 0.0
        self.moving = {"dir": direction, "left": steps, "t": 0.0, "hop_t": hop_t, "then": then, "h": hop_h}
        self.highlight = (self.game.player.pos + direction * steps) % N_SQUARES

    def _land(self) -> None:
        self.highlight = self.game.player.pos
        sq = self.game.square_here()
        name = self.game.player.name
        if sq.kind == "word":
            self._show_word(sq)
        elif sq.kind == "map":
            self._show_map()
        elif sq.kind == "treasure":
            earned = self.game.treasure()
            self.chest_glow = self.t
            self._coin_fx(sq.index, earned)
            self._say(f"Treasure! {name} finds {earned} gold coins!", "#c2410c")
            self._after(1.4)
        elif sq.kind == "cannon":
            self._say("BOOM! The cannon blasts you forward 4!", "#c2410c")
            sound.play("go")
            self.shake = 0.3
            self._event(0.8, lambda: self._move(1, CANNON_JUMP, 0.2, self._land, hop_h=1.1))
        elif sq.kind == "quicksand":
            self._say("Quicksand! Slide back 3...", "#8a5a2b")
            sound.play("whoosh")
            self._event(0.8, lambda: self._move(-1, QUICKSAND_SLIDE, 0.36, self._land, hop_h=0.12))
        else:
            self._say("Home port! Ready to set sail again.", "#1f6fb8")
            self._after(0.9)

    def _show_word(self, sq: Square) -> None:
        self.phase = "word"
        self.phase_t = 0.0
        self.word_square = sq
        sound.play("flip")
        self.buttons = [
            CanvasButton(QRectF(SCREEN_CENTRE[0] - 240, 488, 220, 72), "Got it!", "#2ec97a",
                         lambda: self._answer_word(True), icon="✓", size=24),
            CanvasButton(QRectF(SCREEN_CENTRE[0] + 20, 488, 220, 72), "Not yet", "#ff8a5b",
                         lambda: self._answer_word(False), icon="↺", size=22),
        ]

    def _answer_word(self, ok: bool) -> None:
        if self.phase != "word":
            return
        sq = self.word_square
        res = self.game.answer_word(ok)
        self.buttons = []
        sx, sy = self._square_screen(sq.index)
        if not ok:
            sound.play("click")
            self._say("Nearly! We'll practise that one again.", "#6b5ca5")
            self._after(0.8)
            return
        self.good(sx, sy - 20, "+1 coin")
        name = self.game.player.name
        if res["built"]:
            self.built_at[sq.index] = self.t
            msg = {1: f"{name} built a hut!", 2: "The hut grew - two huts!", 3: "A SANDCASTLE!"}[res["built"]]
        elif res["rent_to"] is not None:
            owner = self.game.players[res["rent_to"]]
            msg = f"{owner.name} gets 1 coin of rent!"
            self._coin_fx(sq.index, 1, owner_index=res["rent_to"])
        else:
            msg = "Great reading!"
        if res["full_set"]:
            msg = f"Full colour set! +{FULL_SET_BONUS} bonus coins!"
            sound.play("star")
            self.burst(sx, sy, ["#ffd43b", "#ffffff", GROUP_COLORS[sq.group]], 40, shape="star", size=10)
        self._say(msg, self.game.player.color)
        self._after(1.3)

    def _show_map(self) -> None:
        self.card = self.game.draw_card()
        card, _word = self.card
        self.phase = "map"
        self.phase_t = 0.0
        sound.play("flip")
        x = SCREEN_CENTRE[0]
        if card.kind == "challenge":
            self.buttons = [
                CanvasButton(QRectF(x - 240, 488, 220, 72), "Got it!", "#2ec97a", lambda: self._answer_map(True),
                             icon="✓", size=24),
                CanvasButton(QRectF(x + 20, 488, 220, 72), "Not yet", "#ff8a5b", lambda: self._answer_map(False),
                             icon="↺", size=22),
            ]
        else:
            self.buttons = [CanvasButton(QRectF(x - 110, 488, 220, 72), "Hooray!", "#2ec97a",
                                         lambda: self._answer_map(True), size=24)]

    def _answer_map(self, ok: bool) -> None:
        if self.phase != "map":
            return
        card, _word = self.card
        from_pos = self.game.player.pos
        earned = self.game.resolve_card(card, ok)
        self.buttons = []
        if earned:
            self._coin_fx(START if card.kind == "home" else from_pos, earned)
        if card.kind == "home":
            self.flying = {"from": from_pos, "t": 0.0}
            self.highlight = START
            self.phase = "flying"
            self.phase_t = 0.0
            sound.play("whoosh")
            return
        if card.kind == "again":
            self.extra_turn = True
            self._say("Roll again!", self.game.player.color)
        elif not ok:
            sound.play("click")
        self._after(0.9)

    def _coin_fx(self, square_index: int, coins: int, owner_index: int | None = None) -> None:
        sx, sy = self._square_screen(square_index)
        sound.play("star")
        self.burst(sx, sy - 10, ["#ffd43b", "#ffcc33", "#fff3b0"], 16 + 6 * coins, shape="dot", size=8)
        label = f"+{coins} coin" + ("s" if coins > 1 else "")
        if owner_index is not None:
            label += " rent"
        self.float_text(label, sx, sy - 40, "#e0a100", 30)

    def _event(self, wait: float, then) -> None:
        self.phase = "event"
        self.phase_t = 0.0
        self.wait = wait
        self.next_step = then

    def _after(self, wait: float) -> None:
        self.phase = "after"
        self.phase_t = 0.0
        self.wait = wait

    def _end_turn(self) -> None:
        extra, self.extra_turn = self.extra_turn, False
        self.game.end_turn(extra)
        self.highlight = None
        if self.game.done:
            self._finish_game()
        else:
            self._begin_turn()

    def _finish_game(self) -> None:
        g = self.game
        p1 = g.players[0]
        if len(g.players) == 1:
            lines = [f"{p1.coins} gold coins!", f"{p1.words_read} words read, {g.huts(0)} huts built"]
        else:
            win = g.winners()
            if len(win) == 1:
                lines = [f"{g.players[win[0]].name} wins with {g.players[win[0]].coins} coins!"]
            else:
                lines = ["It's a tie: " + " & ".join(g.players[i].name for i in win) + "!"]
            lines.append(f"{p1.name}: {p1.coins} coins, {p1.words_read} words read")
        self.phase = "over"
        self.buttons = []
        self.finish(p1.coins, lines)

    # -- input --------------------------------------------------------------
    def _setup_rects(self) -> list[QRectF]:
        return [QRectF(W / 2 - 290 + i * 148, 292, 132, 170) for i in range(4)]

    def click(self, x: float, y: float) -> None:
        if self.phase == "setup":
            for i, r in enumerate(self._setup_rects()):
                if r.contains(x, y):
                    sound.play("click")
                    self._setup(i + 1)
                    return
        elif self.phase == "await_roll":
            sx, sy, _ = self._last_cam.project(*self.die_pos) if hasattr(self, "_last_cam") else (0, 0, 0)
            if math.hypot(x - sx, y - sy) < 55:
                self._roll()

    def key(self, k: int) -> None:
        yes = (Qt.Key_Right, Qt.Key_Y, Qt.Key_Return, Qt.Key_Enter)
        no = (Qt.Key_Left, Qt.Key_N)
        if self.phase == "setup" and Qt.Key_1 <= k <= Qt.Key_4:
            self._setup(k - Qt.Key_1 + 1)
        elif self.phase == "await_roll" and k in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._roll()
        elif self.phase == "word":
            if k in yes:
                self._answer_word(True)
            elif k in no:
                self._answer_word(False)
        elif self.phase == "map":
            challenge = self.card[0].kind == "challenge"
            if k in yes or (not challenge and k == Qt.Key_Space):
                self._answer_map(True)
            elif challenge and k in no:
                self._answer_map(False)

    # -- per-frame update ---------------------------------------------------
    def tick(self, dt: float) -> None:
        self.phase_t += dt
        if self.game is not None:
            for i, pl in enumerate(self.game.players):
                self.coin_shown[i] += (pl.coins - self.coin_shown[i]) * min(1.0, dt * 6)

        if self.phase == "rolling":
            self._tick_die()
        elif self.phase == "moving":
            m = self.moving
            m["t"] += dt
            if m["t"] >= m["hop_t"]:
                m["t"] = 0.0
                earned = self.game.step(m["dir"])
                sound.play("flip")
                if earned:
                    self._coin_fx(START, earned)
                    self._say(f"{self.game.player.name} sails past SET SAIL: +1 coin!", "#1f6fb8")
                m["left"] -= 1
                if m["left"] <= 0:
                    self.moving = None
                    m["then"]()
        elif self.phase == "flying":
            self.flying["t"] += dt
            if self.flying["t"] >= 0.9:
                self.flying = None
                self._say("Home to SET SAIL!", "#1f6fb8")
                self._after(0.6)
        elif self.phase == "event" and self.phase_t >= self.wait:
            then, self.next_step = self.next_step, None
            then()
        elif self.phase == "after" and self.phase_t >= self.wait:
            self._end_turn()

    def _tick_die(self) -> None:
        a = self.die_anim
        u = min(1.0, self.phase_t / ROLL_T)
        e = ease_out_cubic(u)
        fx, fy, fz = a["from"]
        lx, lz = a["to"]
        h = fy * (1 - u) ** 2 * abs(math.cos(2.5 * math.pi * u))
        self.die_pos = (lerp(fx, lx, e), DIE_HALF + h, lerp(fz, lz, e))
        self.die_rot = mat_mul(a["final"], axis_angle(a["axis"], a["spin"] * (1 - e)))
        for i, mark in enumerate((0.2, 0.6)):
            if a["bounces"] == i and u >= mark:
                a["bounces"] += 1
                sound.play("pop")
        if u >= 1.0:
            self.die_anim = None
            sound.play("click")
            if hasattr(self, "_last_cam"):
                sx, sy, _ = self._last_cam.project(*self.die_pos)
                self.float_text(f"{self.roll_value}!", sx, sy - 50, "#ff7a1a", 44)
            self._say(f"{self.game.player.name} rolled a {self.roll_value}!", self.game.player.color)
            self._move(1, self.roll_value, HOP_T, self._land)

    # -- positions ----------------------------------------------------------
    def _pawn_world(self, idx: int) -> tuple[float, float, float]:
        g = self.game
        pl = g.players[idx]
        here = [i for i, other in enumerate(g.players) if other.pos == pl.pos]
        moving_me = idx == g.current and self.moving is not None
        crowd = len(here) - (1 if moving_me else 0)
        slot = here.index(idx) if not moving_me else 0
        if moving_me:
            m = self.moving
            u = min(1.0, m["t"] / m["hop_t"])
            a = pawn_spot(pl.pos)
            b = pawn_spot((pl.pos + m["dir"]) % N_SQUARES)
            e = ease_in_out(u)
            return lerp(a[0], b[0], e), m["h"] * math.sin(math.pi * u), lerp(a[1], b[1], e)
        if idx == g.current and self.flying is not None:
            u = min(1.0, self.flying["t"] / 0.9)
            a = pawn_spot(self.flying["from"])
            b = pawn_spot(START)
            e = ease_in_out(u)
            return lerp(a[0], b[0], e), 2.2 * math.sin(math.pi * u), lerp(a[1], b[1], e)
        x, z = pawn_spot(pl.pos, slot, max(1, crowd))
        return x, 0.0, z

    def _square_screen(self, i: int) -> tuple[float, float]:
        cam = getattr(self, "_last_cam", None) or self._camera()
        x, z = pawn_spot(i)
        sx, sy, _ = cam.project(x, 0.3, z)
        return sx, sy

    def _camera(self) -> Camera:
        # Still after the opening swoop, so the sea, island and board can be cached as one picture.
        pitch, dist, yaw = CAM_PITCH, CAM_DIST, 0.0
        if self.state == "intro":
            k = ease_in_out(min(1.0, self.state_t / 2.5))
            pitch, dist, yaw = lerp(1.42, pitch, k), lerp(19.0, dist, k), lerp(-1.1, yaw, k)
        return Camera((0.0, 0.0, 0.25), dist, pitch, yaw)

    def _draw_backdrop(self, p: QPainter, s: float, ox: float, oy: float) -> None:
        pass  # the sea drawn in draw_game covers the whole window

    # -- drawing ------------------------------------------------------------
    def draw_game(self, p: QPainter) -> None:
        cam = self._camera()
        self._last_cam = cam
        board = QTransform.quadToQuad(_TEX_QUAD, QPolygonF([cam.pt(-HALF, 0, -HALF), cam.pt(HALF, 0, -HALF),
                                                             cam.pt(HALF, 0, HALF), cam.pt(-HALF, 0, HALF)]))
        self._draw_scenery(p, cam, board)
        self._draw_waves(p, cam)
        self._draw_ship(p, cam, self._ship_state())
        if board is not None:
            p.save()
            p.setWorldTransform(board, True)
            self._draw_board_live(p)
            p.restore()
        self._draw_shadows(p, cam)
        self._draw_objects(p, cam)
        if self.game is not None:
            self._draw_panels(p)
        self._draw_banner(p)
        if self.phase == "setup" and self.state == "play":
            self._draw_setup(p)
        elif self.phase == "word":
            self._draw_word_card(p)
        elif self.phase == "map":
            self._draw_map_card(p)

    def _draw_scenery(self, p: QPainter, cam: Camera, board: QTransform | None) -> None:
        if self.state == "intro":
            self._paint_scenery(p, cam, board)
            return
        s, ox, oy = self._transform()
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, cam.ex, cam.ey, cam.ez)
        if self._bg_key != key or self._bg is None:
            pm = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
            pm.setDevicePixelRatio(dpr)
            bp = QPainter(pm)
            bp.setRenderHint(QPainter.Antialiasing)
            bp.translate(ox, oy)
            bp.scale(s, s)
            self._paint_scenery(bp, cam, board)
            bp.end()
            self._bg, self._bg_key = pm, key
        shake = p.worldTransform()
        p.save()
        p.resetTransform()
        p.drawPixmap(QPointF(shake.dx() - ox, shake.dy() - oy), self._bg)
        p.restore()

    def _paint_scenery(self, p: QPainter, cam: Camera, board: QTransform | None) -> None:
        g = QLinearGradient(0, -100, 0, 760)
        g.setColorAt(0, QColor("#1c7fc0"))
        g.setColorAt(0.6, QColor("#2aa6da"))
        g.setColorAt(1, QColor("#49c2e4"))
        p.fillRect(QRectF(-2000, -2000, 5000, 5000), g)
        for size, alpha in ((5.9, 45), (5.25, 80), (4.65, 130)):
            pts = [cam.pt(x, SEA_Y, z) for x, z in _rounded_square(size, 0.9)]
            poly(p, pts, QColor(134, 230, 236, alpha), None)
        self._draw_island_sides(p, cam)
        if board is not None:
            p.save()
            p.setWorldTransform(board, True)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(QRectF(0, 0, TEX, TEX), self._board_texture())
            p.restore()

    def _draw_waves(self, p: QPainter, cam: Camera) -> None:
        # Ripples are batched into a few paths by brightness - one draw call each, not one per ripple.
        buckets = [QPainterPath() for _ in range(4)]
        fl = cam.flatten
        for x, z, ph, sp in self._waves:
            sx, sy, d = cam.project(x + 0.3 * math.sin(self.t * 0.5 * sp + ph), SEA_Y, z)
            if not (-60 < sx < W + 60 and -60 < sy < 760):
                continue
            k = cam.focal / d
            w, rise, th = 0.32 * k, 0.12 * k * fl, 0.05 * k
            path = buckets[min(3, int((0.5 + 0.5 * math.sin(self.t * 1.3 * sp + ph)) * 4))]
            path.moveTo(sx - w, sy)
            path.quadTo(sx - w / 2, sy - rise, sx, sy)
            path.quadTo(sx + w / 2, sy - rise, sx + w, sy)
            path.quadTo(sx + w / 2, sy - rise + th, sx, sy + th * 0.5)
            path.quadTo(sx - w / 2, sy - rise + th, sx - w, sy)
        p.setPen(Qt.NoPen)
        for i, path in enumerate(buckets):
            p.setBrush(QColor(255, 255, 255, 55 + 45 * i))
            p.drawPath(path)

    def _draw_island_sides(self, p: QPainter, cam: Camera) -> None:
        outer = [cam.pt(x, SEA_Y, z) for x, z in _rounded_square(HALF + 0.28, 0.35)]
        inner = [cam.pt(x, SEA_Y, z) for x, z in _rounded_square(HALF + 0.02, 0.05)]
        foam = QPainterPath()
        foam.addPolygon(QPolygonF(outer))
        foam.closeSubpath()
        foam.addPolygon(QPolygonF(inner))
        foam.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 190))
        p.drawPath(foam)
        h = HALF
        sides = (
            ((0, 0, 1), [(-h, 0, h), (h, 0, h), (h, SEA_Y, h), (-h, SEA_Y, h)]),
            ((0, 0, -1), [(h, 0, -h), (-h, 0, -h), (-h, SEA_Y, -h), (h, SEA_Y, -h)]),
            ((1, 0, 0), [(h, 0, h), (h, 0, -h), (h, SEA_Y, -h), (h, SEA_Y, h)]),
            ((-1, 0, 0), [(-h, 0, -h), (-h, 0, h), (-h, SEA_Y, h), (-h, SEA_Y, -h)]),
        )
        for n, pts in sides:
            if cam.faces_camera(n, pts[0]):
                quad = [cam.pt(*q) for q in pts]
                g = QLinearGradient(quad[0], quad[3])
                g.setColorAt(0, shade("#e2ac62", n))
                g.setColorAt(1, shade("#b9814a", n))
                poly(p, quad, g, INK, 2.5)

    # The board top is painted once in texture space (0..780) and mapped onto the island in perspective.
    def _board_texture(self) -> QImage:
        if self._board_img is None:
            size = int(TEX * TEX_SCALE)
            img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            bp = QPainter(img)
            bp.setRenderHint(QPainter.Antialiasing)
            bp.setRenderHint(QPainter.TextAntialiasing)
            bp.scale(TEX_SCALE, TEX_SCALE)
            bp.setPen(QPen(INK, 4))
            bp.setBrush(SAND)
            bp.drawRect(QRectF(0, 0, TEX, TEX))
            bp.setPen(Qt.NoPen)
            bp.setBrush(QColor(196, 150, 84, 70))
            bp.drawPath(self._speckles)
            self._draw_centre(bp)
            for sq in self.squares:
                self._draw_square(bp, sq)
            bp.end()
            self._board_img = img
        return self._board_img

    def _draw_board_live(self, p: QPainter) -> None:
        p.setPen(QPen(QColor(255, 255, 255, 170), 3, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        for i, (x, y) in enumerate(((250, 370), (310, 410), (275, 440), (330, 360))):
            dx = 6 * math.sin(self.t * 1.4 + i)
            path = QPainterPath(QPointF(x - 14 + dx, y))
            path.quadTo(QPointF(x - 7 + dx, y - 7), QPointF(x + dx, y))
            path.quadTo(QPointF(x + 7 + dx, y - 7), QPointF(x + 14 + dx, y))
            p.drawPath(path)
        for sq in self.squares:
            if sq.owner is not None and self.game is not None:
                p.setPen(QPen(qc(self.game.players[sq.owner].color), 7))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(square_rect(sq.index).adjusted(9, 9, -9, -9), 10, 10)
        if self.highlight is not None:
            pulse = 0.5 + 0.5 * math.sin(self.t * 7)
            r = square_rect(self.highlight).adjusted(3, 3, -3, -3)
            p.setPen(QPen(QColor(255, 214, 10), 7 + 4 * pulse))
            p.setBrush(QColor(255, 255, 255, int(50 + 60 * pulse)))
            p.drawRoundedRect(r, 14, 14)

    def _draw_centre(self, p: QPainter) -> None:
        p.setPen(QPen(INK, 3))
        p.setBrush(QColor("#a8eef4"))
        p.drawPath(self._lagoon_outer)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#4cc3e6"))
        p.drawPath(self._lagoon_inner)
        p.setPen(QPen(QColor("#a0522d"), 5, Qt.DashLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(self._trail)
        for a, b in (((503, 335), (543, 372)), ((543, 335), (503, 372))):
            p.setPen(QPen(INK, 13, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(*a), QPointF(*b))
            p.setPen(QPen(QColor("#e63946"), 8, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(*a), QPointF(*b))
        for sx, sy, rot in ((600, 455, 10), (172, 612, -20), (606, 170, 30)):
            star(p, sx, sy, 13, "#ff9f6e", INK, 2.5, rot=rot)
        self._draw_title(p, 390, 192)

    def _draw_title(self, p: QPainter, cx: float, cy: float) -> None:
        words = (("PIRATE", "#ff5d5d"), ("ISLAND", "#ffcc33"))
        widths = [self._tpath(wd, 48)[1] for wd, _c in words]
        gap = 22
        x = cx - (sum(widths) + gap) / 2
        for (wd, col), w in zip(words, widths):
            path, _w = self._tpath(wd, 48)
            p.save()
            p.translate(x + w / 2, cy)
            p.setPen(QPen(INK, 12, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            p.setPen(QPen(WHITE, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)
            p.setPen(Qt.NoPen)
            p.setBrush(qc(col))
            p.drawPath(path)
            p.restore()
            x += w + gap

    def _draw_square(self, p: QPainter, sq: Square) -> None:
        r = square_rect(sq.index).adjusted(5, 5, -5, -5)
        fills = {"word": "#fffaf0", "map": "#f4dcae", "start": "#c9f2ff", "treasure": "#ffe7a3",
                 "cannon": "#ffd2bf", "quicksand": "#ead2a4"}
        rounded(p, r, 12, fills[sq.kind], INK, 3)
        if sq.kind == "word":
            rounded(p, band_rect(sq.index), 7, GROUP_COLORS[sq.group], INK, 2)
            area = word_area(sq.index)
            path, _w = self._tpath(sq.word, 28, area.width() - 12)
            side = sq.index // (SIDE - 1)
            cy = area.center().y() - (14 if side in (0, 2) else 0)
            self._fill_path(p, path, area.center().x(), cy, INK)
        elif sq.kind == "map":
            self._icon_map(p, r)
        else:
            self._draw_corner(p, sq.kind, r)

    def _draw_corner(self, p: QPainter, kind: str, r: QRectF) -> None:
        cx, cy = r.center().x(), r.center().y()
        if kind == "start":
            self._label(p, "SET SAIL!", cx, r.top() + 24, 20, "#1f6fb8")
            path = QPainterPath(QPointF(cx + 38, cy + 6))
            path.quadTo(QPointF(cx, cy - 22), QPointF(cx - 34, cy + 6))
            p.setPen(QPen(INK, 11, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            p.setPen(QPen(QColor("#ff5d5d"), 6, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(path)
            arrow = QPolygonF([QPointF(cx - 46, cy + 10), QPointF(cx - 24, cy - 6), QPointF(cx - 24, cy + 22)])
            poly(p, list(arrow), "#ff5d5d", INK, 2.5)
            _coin(p, cx - 16, r.bottom() - 26, 13)
            self._label(p, "+1", cx + 14, r.bottom() - 26, 20, INK)
        elif kind == "treasure":
            self._label(p, "TREASURE", cx, r.top() + 22, 19, "#c2410c")
            rounded(p, QRectF(cx - 34, cy - 6, 68, 40), 6, "#a0612d", INK, 3)
            path = QPainterPath(QPointF(cx - 36, cy - 4))
            path.cubicTo(QPointF(cx - 36, cy - 34), QPointF(cx + 36, cy - 34), QPointF(cx + 36, cy - 4))
            path.closeSubpath()
            p.setPen(QPen(INK, 3))
            p.setBrush(QColor("#c07a3a"))
            p.drawPath(path)
            for dx in (-22, 22):
                p.fillRect(QRectF(cx + dx - 4, cy - 26, 8, 60), QColor("#ffcc33"))
            rounded(p, QRectF(cx - 8, cy - 4, 16, 16), 3, "#ffcc33", INK, 2)
            self._label(p, "+2 coins", cx, r.bottom() - 18, 18, INK)
        elif kind == "cannon":
            self._label(p, "CANNON!", cx, r.top() + 22, 20, "#c2410c")
            p.save()
            p.translate(cx - 4, cy + 4)
            p.rotate(-18)
            rounded(p, QRectF(-38, -14, 70, 28), 13, "#3a3550", INK, 3)
            ellipse(p, 34, 0, 7, 14, "#2d2840", INK, 2)
            p.restore()
            circle(p, cx - 10, cy + 22, 14, "#8a5a35", INK, 3)
            circle(p, cx - 10, cy + 22, 4, INK)
            for i in range(3):
                star(p, cx + 38 + i * 4, cy - 22 + i * 9, 6 - i, "#ffb703", INK, 1.5)
            self._label(p, "Zoom 4!", cx, r.bottom() - 18, 18, INK)
        elif kind == "quicksand":
            self._label(p, "QUICKSAND", cx, r.top() + 22, 18, "#8a5a2b")
            p.setPen(QPen(QColor("#8a5a2b"), 5, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            for j in range(60):
                a = j * 0.32
                rad = 3 + j * 0.62
                pt = QPointF(cx + math.cos(a) * rad, cy + 4 + math.sin(a) * rad * 0.8)
                path.moveTo(pt) if j == 0 else path.lineTo(pt)
            p.drawPath(path)
            self._label(p, "Back 3", cx, r.bottom() - 18, 18, INK)

    def _icon_map(self, p: QPainter, r: QRectF) -> None:
        cx, cy = r.center().x(), r.center().y()
        m = QRectF(cx - 30, cy - 34, 60, 50)
        rounded(p, m, 6, "#fff3d6", INK, 2.5)
        p.setPen(QPen(QColor("#a0522d"), 2.5, Qt.DashLine, Qt.RoundCap))
        p.drawLine(QPointF(m.left() + 8, m.bottom() - 10), QPointF(cx + 8, cy - 12))
        p.setPen(QPen(QColor("#e63946"), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx + 6, cy - 22), QPointF(cx + 20, cy - 8))
        p.drawLine(QPointF(cx + 20, cy - 22), QPointF(cx + 6, cy - 8))
        self._label(p, "MAP ?", cx, r.bottom() - 18, 17, "#8a5a2b")

    def _label(self, p: QPainter, s: str, cx: float, cy: float, size: float, color) -> None:
        path, _w = self._tpath(s, size)
        self._fill_path(p, path, cx, cy, color)

    def _fill_path(self, p: QPainter, path: QPainterPath, cx: float, cy: float, color) -> None:
        p.save()
        p.translate(cx, cy)
        p.setPen(Qt.NoPen)
        p.setBrush(qc(color))
        p.drawPath(path)
        p.restore()

    def _tpath(self, s: str, size: float, max_w: float | None = None) -> tuple[QPainterPath, float]:
        key = (s, size, max_w)
        hit = self._paths.get(key)
        if hit is None:
            if max_w:
                size = fit_size(s, max_w, size, min_size=6)
            f = font(size)
            fm = QFontMetricsF(f)
            w = fm.horizontalAdvance(s)
            path = QPainterPath()
            path.addText(QPointF(-w / 2, (fm.ascent() - fm.descent()) / 2), f, s)
            hit = self._paths[key] = (path, w)
        return hit

    # 3D objects -------------------------------------------------------------
    def _draw_shadows(self, p: QPainter, cam: Camera) -> None:
        p.setPen(Qt.NoPen)
        items = [(CHEST_POS[0] + 0.06, CHEST_POS[1] - 0.05, 0.5, 70), (DECK_POS[0] + 0.05, DECK_POS[1] - 0.04, 0.5, 55)]
        for x, z, _h, _lean in PALMS:
            items.append((x + 0.06, z - 0.05, 0.22, 60))
        if self.game is not None:
            for i in range(len(self.game.players)):
                x, y, z = self._pawn_world(i)
                items.append((x + 0.06, z - 0.05, 0.24 * PAWN_SCALE * max(0.45, 1 - y * 0.35),
                              int(85 * max(0.3, 1 - y * 0.4))))
        dx, dy, dz = self.die_pos
        lift = dy - DIE_HALF
        items.append((dx + 0.08, dz - 0.06, 0.38 * max(0.4, 1 - lift * 0.3), int(90 * max(0.25, 1 - lift * 0.35))))
        for x, z, r, a in items:
            sx, sy, d = cam.project(x, 0.0, z)
            k = cam.focal / d
            p.setBrush(QColor(60, 40, 10, a))
            p.drawEllipse(QPointF(sx, sy), r * k, r * k * cam.flatten)

    def _draw_objects(self, p: QPainter, cam: Camera) -> None:
        items = []
        for sq in self.squares:
            if sq.owner is None or self.game is None:
                continue
            color = self.game.players[sq.owner].color
            grow = ease_out_back(min(1.0, (self.t - self.built_at.get(sq.index, -9)) * 2.2))
            if sq.level >= MAX_LEVEL:
                (x, z), = hut_spots(sq.index, 1)
                items.append((cam.project(x, 0, z)[2], lambda x=x, z=z, c=color, g=grow: self._draw_castle(p, cam, x, z, c, g)))
            else:
                for x, z in hut_spots(sq.index, sq.level):
                    items.append((cam.project(x, 0, z)[2], lambda x=x, z=z, c=color, g=grow: self._draw_hut(p, cam, x, z, c, g)))
        items.append((cam.project(CHEST_POS[0], 0, CHEST_POS[1])[2], lambda: self._draw_chest(p, cam)))
        items.append((cam.project(DECK_POS[0], 0, DECK_POS[1])[2], lambda: self._draw_deck(p, cam)))
        for x, z, h, lean in PALMS:
            items.append((cam.project(x, 0, z)[2], lambda x=x, z=z, h=h, lean=lean: self._draw_palm(p, cam, x, z, h, lean)))
        if self.game is not None:
            for i, pl in enumerate(self.game.players):
                x, y, z = self._pawn_world(i)
                items.append((cam.project(x, 0, z)[2] - 0.05, lambda x=x, y=y, z=z, i=i: self._draw_pawn(p, cam, x, y, z, i)))
        dx, dy, dz = self.die_pos
        items.append((cam.project(dx, 0, dz)[2], lambda: self._draw_die(p, cam)))
        items.sort(key=lambda it: -it[0])
        for _d, draw in items:
            draw()

    def _draw_die(self, p: QPainter, cam: Camera) -> None:
        def pips(name: str, painter: QPainter) -> None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 120))
            painter.drawRoundedRect(QRectF(8, 8, 84, 84), 20, 20)
            painter.setBrush(QColor("#2d2840"))
            for x, y in PIPS[DIE_VALUES[name]]:
                painter.drawEllipse(QPointF(x, y), 9.5, 9.5)

        h = DIE_HALF
        draw_box(p, cam, self.die_pos, (h, h, h), self.die_rot, "#fffdf6", pips, width=2.6)

    def _draw_hut(self, p: QPainter, cam: Camera, x: float, z: float, color: str, grow: float) -> None:
        # Gable end faces the camera, so it reads as a house shape rather than a box with a lid.
        s = max(0.01, grow)
        w, hw, hr, o, drop = 0.16 * s, 0.19 * s, 0.19 * s, 0.04 * s, 0.03 * s
        walls = "#fff1d6"
        v = lambda dx, dy, dz: (x + dx, dy, z + dz)  # noqa: E731
        faces = [
            ([v(-w, 0, w), v(w, 0, w), v(w, hw, w), v(0, hw + hr, w), v(-w, hw, w)], walls),
            ([v(w, 0, -w), v(-w, 0, -w), v(-w, hw, -w), v(0, hw + hr, -w), v(w, hw, -w)], walls),
            ([v(w, 0, w), v(w, 0, -w), v(w, hw, -w), v(w, hw, w)], walls),
            ([v(-w, 0, -w), v(-w, 0, w), v(-w, hw, w), v(-w, hw, -w)], walls),
        ]
        draw_mesh(p, cam, faces, (x, hw / 2, z), width=1.6)
        if cam.faces_camera((0, 0, 1), (x, 0, z + w)):
            door = [cam.pt(x - 0.045 * s, 0, z + w), cam.pt(x + 0.045 * s, 0, z + w),
                    cam.pt(x + 0.045 * s, 0.12 * s, z + w), cam.pt(x - 0.045 * s, 0.12 * s, z + w)]
            poly(p, door, "#8a5a35", INK, 1.2)
        roof = [
            ([v(-w - o, hw - drop, -w - o), v(-w - o, hw - drop, w + o), v(0, hw + hr, w + o), v(0, hw + hr, -w - o)], color),
            ([v(w + o, hw - drop, w + o), v(w + o, hw - drop, -w - o), v(0, hw + hr, -w - o), v(0, hw + hr, w + o)], color),
        ]
        draw_mesh(p, cam, roof, (x, hw, z), width=1.6)

    def _draw_castle(self, p: QPainter, cam: Camera, x: float, z: float, color: str, grow: float) -> None:
        s = max(0.01, grow)
        h, w = 0.38 * s, 0.22 * s
        draw_box(p, cam, (x, h / 2, z), (w, h / 2, w), IDENTITY, "#f2cf86", width=1.8)
        turrets = [(x + dx * w * 0.8, z + dz * w * 0.8) for dx in (-1, 1) for dz in (-1, 1)]
        turrets.sort(key=lambda t: -cam.project(t[0], h, t[1])[2])
        for tx, tz in turrets:
            draw_box(p, cam, (tx, h + 0.05 * s, tz), (0.055 * s, 0.05 * s, 0.055 * s), IDENTITY, "#f7dda4", width=1.4)
        if cam.faces_camera((0, 0, 1), (x, 0, z + w)):
            arch = [cam.pt(x - 0.06 * s, 0, z + w), cam.pt(x + 0.06 * s, 0, z + w), cam.pt(x + 0.06 * s, 0.12 * s, z + w),
                    cam.pt(x, 0.16 * s, z + w), cam.pt(x - 0.06 * s, 0.12 * s, z + w)]
            poly(p, arch, "#8a5a35", INK, 1.4)
        base = cam.pt(x, h, z)
        top = cam.pt(x, h + 0.42 * s, z)
        p.setPen(QPen(INK, 2.5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(base, top)
        k = cam.focal / cam.project(x, h, z)[2]
        wave = math.sin(self.t * 6) * 0.03 * k
        flag = [top, QPointF(top.x() + 0.22 * k * s, top.y() + 0.05 * k * s + wave), QPointF(top.x(), top.y() + 0.12 * k * s)]
        poly(p, flag, color, INK, 1.6)

    def _draw_chest(self, p: QPainter, cam: Camera) -> None:
        x, z = CHEST_POS
        rot = rot_y(-0.35)

        def bands(name: str, painter: QPainter) -> None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ffcc33"))
            if name in ("front", "back", "top"):
                for bx in (18, 74):
                    painter.drawRect(QRectF(bx, 0, 9, 100))
            if name == "front":
                painter.setPen(QPen(INK, 2))
                painter.drawRoundedRect(QRectF(42, 0, 16, 26), 3, 3)

        draw_box(p, cam, (x, 0.19, z), (0.36, 0.19, 0.24), rot, "#a0612d", bands)
        draw_box(p, cam, (x, 0.45, z), (0.38, 0.08, 0.26), rot, "#c07a3a", bands)
        glow = self.t - self.chest_glow
        if glow < 2.0:
            sx, sy, d = cam.project(x, 0.6, z)
            k = cam.focal / d
            for i in range(6):
                a = i * 1.05 + glow * 3
                star(p, sx + math.cos(a) * 0.45 * k, sy - 0.2 * k + math.sin(a) * 0.25 * k, 0.07 * k * (1.2 - glow / 2),
                     "#fff3b0", INK, 1.5)
        elif int(self.t * 1.5) % 4 == 0:
            sx, sy, d = cam.project(x + 0.2, 0.55, z)
            star(p, sx, sy, 6 + 4 * math.sin(self.t * 9), "#fffbe6", None, 0)

    def _draw_deck(self, p: QPainter, cam: Camera) -> None:
        def face(name: str, painter: QPainter) -> None:
            if name == "top":
                painter.setPen(QPen(QColor("#a0522d"), 3, Qt.DashLine, Qt.RoundCap))
                painter.drawLine(QPointF(18, 78), QPointF(56, 40))
                painter.setPen(QPen(QColor("#e63946"), 7, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(58, 22), QPointF(80, 44))
                painter.drawLine(QPointF(80, 22), QPointF(58, 44))
                path, _w = self._tpath("MAPS", 15)
                self._fill_path(painter, path, 36, 24, "#8a5a2b")
            else:
                painter.setPen(QPen(QColor(150, 120, 80, 150), 2))
                for yy in (25, 50, 75):
                    painter.drawLine(QPointF(4, yy), QPointF(96, yy))

        draw_box(p, cam, (DECK_POS[0], 0.08, DECK_POS[1]), (0.42, 0.08, 0.3), rot_y(0.35), "#fff3d6", face)

    def _draw_palm(self, p: QPainter, cam: Camera, x: float, z: float, h: float, lean: float) -> None:
        bx, by, d = cam.project(x, 0, z)
        tx, ty, _ = cam.project(x + lean, h, z)
        k = cam.focal / d
        trunk = QPainterPath(QPointF(bx - 0.07 * k, by))
        mx, my = (bx + tx) / 2 + lean * 0.3 * k, (by + ty) / 2
        trunk.quadTo(QPointF(mx - 0.05 * k, my), QPointF(tx - 0.035 * k, ty))
        trunk.lineTo(QPointF(tx + 0.035 * k, ty))
        trunk.quadTo(QPointF(mx + 0.05 * k, my), QPointF(bx + 0.07 * k, by))
        trunk.closeSubpath()
        p.setPen(QPen(INK, 2))
        p.setBrush(QColor("#a8743f"))
        p.drawPath(trunk)
        p.setPen(QPen(QColor("#7d5229"), 2))
        for j in range(1, 6):
            u = j / 6
            px, py = lerp(bx, tx, u) + math.sin(u * math.pi) * lean * 0.15 * k, lerp(by, ty, u)
            p.drawLine(QPointF(px - 0.045 * k, py), QPointF(px + 0.045 * k, py + 0.02 * k))
        sway = math.sin(self.t * 1.3 + x) * 0.06
        for j in range(7):
            a = -math.pi / 2 + (j - 3) * 0.55 + sway
            reach = 0.62 * k * (0.85 if j in (0, 6) else 1)
            ex, ey = tx + math.cos(a) * reach, ty + math.sin(a) * reach * 0.55 + 0.32 * k * abs(math.cos(a))
            leaf = QPainterPath(QPointF(tx, ty))
            nx, ny = -(ey - ty), ex - tx
            nl = math.hypot(nx, ny) or 1
            nx, ny = nx / nl * 0.09 * k, ny / nl * 0.09 * k
            cx_, cy_ = (tx + ex) / 2, (ty + ey) / 2 - 0.12 * k
            leaf.quadTo(QPointF(cx_ + nx, cy_ + ny), QPointF(ex, ey))
            leaf.quadTo(QPointF(cx_ - nx, cy_ - ny), QPointF(tx, ty))
            p.setPen(QPen(INK, 2))
            p.setBrush(QColor("#3fbf5f") if j % 2 else QColor("#2fa64f"))
            p.drawPath(leaf)
        for dx in (-0.05, 0.04, 0.0):
            circle(p, tx + dx * k, ty + 0.04 * k + (0.03 * k if dx == 0 else 0), 0.045 * k, "#7a4a22", INK, 1.5)

    def _draw_pawn(self, p: QPainter, cam: Camera, x: float, y: float, z: float, idx: int) -> None:
        pl = self.game.players[idx]
        sx, sy, d = cam.project(x, y, z)
        k = cam.focal / d * PAWN_SCALE
        vs = (sy - cam.project(x, y + 1.0, z)[1]) * PAWN_SCALE
        e = cam.flatten
        col = qc(pl.color)
        squash = 0.0
        if idx == self.game.current and self.moving is not None:
            u = self.moving["t"] / self.moving["hop_t"]
            squash = 0.12 * math.sin(math.pi * u)
        p.save()
        p.translate(sx, sy)
        p.scale(1 - squash * 0.5, 1 + squash)
        if idx == self.game.current and self.phase == "await_roll":
            pulse = 0.5 + 0.5 * math.sin(self.t * 5)
            p.setPen(QPen(QColor(255, 255, 255, int(120 + 120 * pulse)), 3))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), 0.32 * k, 0.32 * k * e)
        # base
        p.setPen(QPen(INK, 2))
        p.setBrush(col.darker(130))
        p.drawEllipse(QPointF(0, 0), 0.22 * k, 0.22 * k * e)
        p.drawRect(QRectF(-0.22 * k, -0.07 * vs, 0.44 * k, 0.07 * vs))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(-0.22 * k + 1, -0.07 * vs, 0.44 * k - 2, 0.07 * vs + 1))
        p.setPen(QPen(INK, 2))
        p.setBrush(col)
        p.drawEllipse(QPointF(0, -0.07 * vs), 0.22 * k, 0.22 * k * e)
        # body
        y0, y1 = -0.08 * vs, -0.42 * vs
        body = QPainterPath(QPointF(-0.17 * k, y0))
        body.cubicTo(QPointF(-0.17 * k, y0 - 0.14 * vs), QPointF(-0.07 * k, y1 + 0.12 * vs), QPointF(-0.075 * k, y1))
        body.lineTo(QPointF(0.075 * k, y1))
        body.cubicTo(QPointF(0.07 * k, y1 + 0.12 * vs), QPointF(0.17 * k, y0 - 0.14 * vs), QPointF(0.17 * k, y0))
        body.closeSubpath()
        g = QLinearGradient(-0.17 * k, 0, 0.17 * k, 0)
        g.setColorAt(0, col.lighter(135))
        g.setColorAt(0.55, col)
        g.setColorAt(1, col.darker(135))
        p.setBrush(g)
        p.drawPath(body)
        p.setBrush(col.darker(115))
        p.drawEllipse(QPointF(0, y1), 0.12 * k, 0.12 * k * e * 0.7)
        # head with a face, an eye patch and a pirate hat
        hy = -0.56 * vs
        hr = 0.15 * k
        rg = QRadialGradient(QPointF(-0.05 * k, hy - 0.05 * k), hr * 1.4)
        rg.setColorAt(0, QColor("#ffe2c6"))
        rg.setColorAt(1, QColor("#f2b98c"))
        p.setBrush(rg)
        p.drawEllipse(QPointF(0, hy), hr, hr)
        blink = (self.t * 0.7 + idx * 0.37) % 3.2 < 0.12
        p.setBrush(INK)
        if blink:
            p.drawRect(QRectF(0.03 * k, hy - 0.004 * k, 0.05 * k, 0.012 * k))
        else:
            p.drawEllipse(QPointF(0.055 * k, hy), 0.024 * k, 0.03 * k)
            p.setBrush(WHITE)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(0.062 * k, hy - 0.01 * k), 0.008 * k, 0.008 * k)
        p.setPen(QPen(INK, max(1.0, 0.012 * k)))
        p.drawLine(QPointF(-0.13 * k, hy - 0.07 * k), QPointF(0.11 * k, hy - 0.1 * k))
        p.setBrush(INK)
        p.drawEllipse(QPointF(-0.055 * k, hy - 0.005 * k), 0.04 * k, 0.034 * k)
        smile = QPainterPath(QPointF(-0.04 * k, hy + 0.06 * k))
        smile.quadTo(QPointF(0.01 * k, hy + 0.1 * k), QPointF(0.06 * k, hy + 0.055 * k))
        p.setBrush(Qt.NoBrush)
        p.drawPath(smile)
        hat = QPainterPath(QPointF(-0.21 * k, hy - 0.08 * k))
        hat.quadTo(QPointF(0, hy - 0.02 * k), QPointF(0.21 * k, hy - 0.08 * k))
        hat.quadTo(QPointF(0.13 * k, hy - 0.13 * k), QPointF(0.11 * k, hy - 0.2 * k))
        hat.quadTo(QPointF(0, hy - 0.3 * k), QPointF(-0.11 * k, hy - 0.2 * k))
        hat.quadTo(QPointF(-0.13 * k, hy - 0.13 * k), QPointF(-0.21 * k, hy - 0.08 * k))
        p.setPen(QPen(INK, 2))
        p.setBrush(QColor("#2b2540"))
        p.drawPath(hat)
        p.setPen(QPen(col, max(1.5, 0.025 * k)))
        p.drawLine(QPointF(-0.14 * k, hy - 0.115 * k), QPointF(0.14 * k, hy - 0.115 * k))
        circle(p, 0, hy - 0.18 * k, 0.03 * k, WHITE)
        p.restore()
        if idx == self.game.current and self.phase == "await_roll":
            bob = math.sin(self.t * 5) * 6
            ay = sy - 0.92 * vs + bob
            arrow = [QPointF(sx - 13, ay - 18), QPointF(sx + 13, ay - 18), QPointF(sx, ay)]
            poly(p, arrow, col, INK, 2.5)

    # Sea traffic ------------------------------------------------------------
    def _ship_state(self) -> tuple[float, float, float]:
        a = self.t * 0.09 + 2.2
        return 6.6 * math.cos(a), 6.6 * math.sin(a), a

    def _draw_ship(self, p: QPainter, cam: Camera, state) -> None:
        x, z, a = state
        bob = 0.05 * math.sin(self.t * 2.1)
        sx, sy, d = cam.project(x, SEA_Y + bob, z)
        if sy > 760 or sy < -120:
            return
        k = cam.focal / d
        ahead = cam.project(x - math.sin(a) * 0.2, SEA_Y, z + math.cos(a) * 0.2)
        facing = 1 if ahead[0] >= sx else -1
        for j in range(1, 4):
            wx, wy, wd = cam.project(x + math.sin(a) * 0.45 * j, SEA_Y, z - math.cos(a) * 0.45 * j)
            wk = cam.focal / wd
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 110 - j * 25))
            p.drawEllipse(QPointF(wx, wy), 0.25 * wk, 0.08 * wk)
        p.save()
        p.translate(sx, sy)
        p.scale(facing * k / 100.0, k / 100.0)
        p.rotate(math.sin(self.t * 1.7) * 3)
        hull = QPainterPath(QPointF(-75, -18))
        hull.lineTo(QPointF(80, -18))
        hull.quadTo(QPointF(70, 14), QPointF(40, 16))
        hull.lineTo(QPointF(-48, 16))
        hull.quadTo(QPointF(-70, 10), QPointF(-75, -18))
        p.setPen(QPen(INK, 4))
        p.setBrush(QColor("#8a5a35"))
        p.drawPath(hull)
        p.setPen(QPen(QColor("#ffcc33"), 4))
        p.drawLine(QPointF(-66, -6), QPointF(70, -6))
        p.setPen(QPen(INK, 5))
        p.drawLine(QPointF(0, -18), QPointF(0, -150))
        sail = QPainterPath(QPointF(-48, -138))
        sail.quadTo(QPointF(0, -128), QPointF(48, -138))
        sail.quadTo(QPointF(58, -88), QPointF(48, -40))
        sail.quadTo(QPointF(0, -50), QPointF(-48, -40))
        sail.quadTo(QPointF(-40, -88), QPointF(-48, -138))
        p.setPen(QPen(INK, 4))
        p.setBrush(WHITE)
        p.drawPath(sail)
        circle(p, 0, -96, 14, INK)
        circle(p, -5, -98, 3.5, WHITE)
        circle(p, 5, -98, 3.5, WHITE)
        flag = QPolygonF([QPointF(0, -150), QPointF(34, -142 + math.sin(self.t * 6) * 4), QPointF(0, -132)])
        p.setBrush(QColor("#ff5d5d"))
        p.drawPolygon(flag)
        p.restore()

    # 2D overlays ------------------------------------------------------------
    def _draw_panels(self, p: QPainter) -> None:
        g = self.game
        for i, pl in enumerate(g.players):
            r = QRectF(14, 78 + i * 78, 200, 68)
            active = i == g.current and self.state == "play" and self.phase != "over"
            col = qc(pl.color)
            if active:
                lift = 3 * math.sin(self.t * 4)
                r.translate(0, -abs(lift))
                rounded(p, r.adjusted(-5, -5, 5, 5), 26, QColor(col.red(), col.green(), col.blue(), 90))
            rounded(p, r, 22, QColor(255, 255, 255, 238), col if active else INK, 4 if active else 3)
            circle(p, r.left() + 34, r.center().y() + 2, 21, col, INK, 3)
            circle(p, r.left() + 34, r.center().y() + 4, 12, "#ffe2c6", INK, 2)
            hat = QPainterPath(QPointF(r.left() + 18, r.center().y() - 6))
            hat.quadTo(QPointF(r.left() + 34, r.center().y() - 26), QPointF(r.left() + 50, r.center().y() - 6))
            hat.closeSubpath()
            p.setPen(QPen(INK, 2))
            p.setBrush(QColor("#2b2540"))
            p.drawPath(hat)
            self._left_label(p, pl.name, r.left() + 64, r.top() + 21, 16, 128)
            _coin(p, r.left() + 74, r.top() + 47, 10)
            self._left_label(p, str(round(self.coin_shown[i])), r.left() + 90, r.top() + 47, 17)
            huts = g.huts(i)
            hx = r.left() + 140
            path = QPainterPath(QPointF(hx - 10, r.top() + 47))
            path.lineTo(QPointF(hx, r.top() + 38))
            path.lineTo(QPointF(hx + 10, r.top() + 47))
            path.closeSubpath()
            p.setPen(QPen(INK, 2))
            p.setBrush(col)
            p.drawPath(path)
            p.setBrush(QColor("#fff1d6"))
            p.drawRect(QRectF(hx - 7, r.top() + 47, 14, 9))
            self._left_label(p, str(huts), hx + 16, r.top() + 47, 17)

    def _left_label(self, p: QPainter, s: str, x: float, cy: float, size: float, max_w: float | None = None) -> None:
        path, w = self._tpath(s, size, max_w)
        self._fill_path(p, path, x + w / 2, cy, INK)

    def _draw_banner(self, p: QPainter) -> None:
        msg, t0, col = self.banner
        if not msg or self.state != "play" or self.phase in ("word", "map"):
            return
        k = ease_out_back(min(1.0, (self.t - t0) * 4))
        cx = SCREEN_CENTRE[0]
        p.save()
        p.translate(cx, 106)
        p.scale(k, k)
        path, tw = self._tpath(msg, 22, 580)
        w = tw + 56
        rounded(p, QRectF(-w / 2, -24, w, 48), 24, QColor(255, 255, 255, 235), col, 4)
        self._fill_path(p, path, 0, 0, col.darker(125))
        p.restore()

    def _card_frame(self, p: QPainter, header: str, header_col) -> QRectF:
        k = ease_out_back(min(1.0, self.phase_t * 3.2))
        flip = max(0.02, min(1.0, self.phase_t * 4))
        cx, cy = SCREEN_CENTRE[0], 300
        p.fillRect(QRectF(-2000, -2000, 5000, 5000), QColor(20, 15, 40, int(70 * min(1.0, self.phase_t * 4))))
        p.translate(cx, cy)
        p.scale(k * flip, k)
        r = QRectF(-215, -150, 430, 300)
        rounded(p, r, 26, WHITE, INK, 5, shadow=10)
        top = QRectF(r.left() + 10, r.top() + 10, r.width() - 20, 70)
        rounded(p, top, 18, header_col, INK, 3)
        text(p, header, 0, top.center().y(), 22, WHITE, INK, 5, max_w=top.width() - 24)
        return r

    def _draw_word_card(self, p: QPainter) -> None:
        sq = self.word_square
        g = self.game
        p.save()
        r = self._card_frame(p, f"{g.player.name}, read it out loud!" if len(g.players) > 1 else "Read it out loud!",
                             GROUP_COLORS[sq.group])
        text(p, sq.word, 0, 18, 76, INK, max_w=r.width() - 50)
        if sq.owner is None:
            hint = "Read it right to build a hut here!"
        elif sq.owner == g.current:
            hint = "Your hut! Read it to make it grow." if sq.level < MAX_LEVEL else "Your sandcastle! Read it for a coin."
        else:
            hint = f"{g.players[sq.owner].name}'s hut - they get 1 coin rent."
        text(p, hint, 0, r.bottom() - 34, 17, "#6b5ca5", max_w=r.width() - 40)
        p.restore()

    def _draw_map_card(self, p: QPainter) -> None:
        card, word = self.card
        p.save()
        r = self._card_frame(p, "TREASURE MAP", "#c2410c")
        if card.kind == "challenge":
            text(p, card.text, 0, -38, 21, INK, max_w=r.width() - 40)
            text(p, word, 0, 30, 64, "#1f6fb8", max_w=r.width() - 60)
            text(p, f"Do it for {card.coins} coins!", 0, r.bottom() - 32, 17, "#6b5ca5")
        else:
            text(p, card.text, 0, -10, 24, INK, max_w=r.width() - 40)
            if card.coins:
                for j in range(card.coins):
                    _coin(p, (j - (card.coins - 1) / 2) * 50, 50, 20)
            else:
                star(p, 0, 50, 26, GOLD, INK, 3)
        p.restore()

    def _draw_setup(self, p: QPainter) -> None:
        p.fillRect(QRectF(-2000, -2000, 5000, 5000), QColor(20, 15, 40, 90))
        card = QRectF(W / 2 - 330, 170, 660, 340)
        rounded(p, card, 34, WHITE, INK, 5, shadow=10)
        text(p, "How many pirates are playing?", W / 2, 228, 30, "#c2410c", INK, 6, max_w=600)
        for i, r in enumerate(self._setup_rects()):
            bob = math.sin(self.t * 3 + i) * 4
            rr = r.translated(0, bob)
            rounded(p, rr, 22, QColor(PLAYER_COLORS[i]).lighter(160), INK, 4)
            text(p, str(i + 1), rr.center().x(), rr.top() + 42, 40, WHITE, INK, 7)
            for j in range(i + 1):
                cx = rr.center().x() + (j - i / 2) * 26
                cy = rr.bottom() - 46
                circle(p, cx, cy + 12, 12, PLAYER_COLORS[j], INK, 2.5)
                circle(p, cx, cy - 4, 9, "#ffe2c6", INK, 2)
        text(p, "Tap a number (or press 1-4 on the keyboard)", W / 2, 488, 16, "#6b5ca5", bold=False)


def _coin(p: QPainter, cx: float, cy: float, r: float) -> None:
    circle(p, cx, cy, r, "#ffcc33", INK, max(1.5, r * 0.18))
    circle(p, cx, cy, r * 0.62, "#ffe27a")
    star(p, cx, cy, r * 0.45, "#f0a500", None, 0)


def _rounded_square(half: float, radius: float, steps: int = 4) -> list[tuple[float, float]]:
    pts = []
    inner = half - radius
    for cx, cz, a0 in ((inner, inner, 0.0), (-inner, inner, 0.5 * math.pi), (-inner, -inner, math.pi),
                       (inner, -inner, 1.5 * math.pi)):
        for s in range(steps + 1):
            a = a0 + (s / steps) * 0.5 * math.pi
            pts.append((cx + math.cos(a) * radius, cz + math.sin(a) * radius))
    return pts


def _blob(cx: float, cy: float, rx: float, ry: float, rng: random.Random, n: int) -> QPainterPath:
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        k = rng.uniform(0.86, 1.1)
        pts.append(QPointF(cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
    mid = lambda a, b: QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)  # noqa: E731
    path = QPainterPath(mid(pts[-1], pts[0]))
    for i, pt in enumerate(pts):
        path.quadTo(pt, mid(pt, pts[(i + 1) % n]))
    path.closeSubpath()
    return path


def draw_pirate_icon(p: QPainter, cx: float, cy: float, s: float, t: float) -> None:
    """The Pirate Island picture on its arcade hub tile: a little island, a die and a pawn."""
    ellipse(p, cx, cy + s * 0.12, s * 0.62, s * 0.3, QColor(255, 255, 255, 90))
    top = [QPointF(cx, cy - s * 0.18), QPointF(cx + s * 0.5, cy + s * 0.06), QPointF(cx, cy + s * 0.3),
           QPointF(cx - s * 0.5, cy + s * 0.06)]
    side_l = [top[3], top[2], QPointF(cx, cy + s * 0.38), QPointF(cx - s * 0.5, cy + s * 0.14)]
    side_r = [top[2], top[1], QPointF(cx + s * 0.5, cy + s * 0.14), QPointF(cx, cy + s * 0.38)]
    poly(p, side_l, "#d29a55", INK, 2.5)
    poly(p, side_r, "#b9814a", INK, 2.5)
    poly(p, top, "#f7dda4", INK, 3)
    for j in range(8):
        u = (j + 0.5) / 8
        a, b = (top[0], top[1]) if j < 4 else (top[3], top[2])
        uu = (u * 2) % 1
        px = a.x() + (b.x() - a.x()) * uu
        py = a.y() + (b.y() - a.y()) * uu + s * 0.03
        ellipse(p, px, py, s * 0.035, s * 0.02, GROUP_COLORS[j], INK, 1.2)
    ellipse(p, cx - s * 0.08, cy + s * 0.06, s * 0.13, s * 0.06, "#4cc3e6", INK, 1.5)
    tx, ty = cx - s * 0.26, cy - s * 0.2
    p.setPen(QPen(INK, 2))
    p.setBrush(QColor("#a8743f"))
    p.drawRect(QRectF(tx - s * 0.015, ty, s * 0.03, s * 0.24))
    for j in range(5):
        a = -math.pi / 2 + (j - 2) * 0.62 + math.sin(t * 1.5) * 0.08
        ellipse(p, tx + math.cos(a) * s * 0.09, ty + math.sin(a) * s * 0.05 + s * 0.02, s * 0.09, s * 0.03, "#3fbf5f", INK, 1.2)
    bob = abs(math.sin(t * 3)) * s * 0.1
    dx, dy, ds = cx + s * 0.22, cy - s * 0.02 - bob, s * 0.11
    cube_top = [QPointF(dx, dy - ds), QPointF(dx + ds, dy - ds * 0.5), QPointF(dx, dy), QPointF(dx - ds, dy - ds * 0.5)]
    cube_l = [cube_top[3], cube_top[2], QPointF(dx, dy + ds), QPointF(dx - ds, dy + ds * 0.5)]
    cube_r = [cube_top[2], cube_top[1], QPointF(dx + ds, dy + ds * 0.5), QPointF(dx, dy + ds)]
    poly(p, cube_l, "#e9e3d6", INK, 2)
    poly(p, cube_r, "#d4ccbb", INK, 2)
    poly(p, cube_top, WHITE, INK, 2)
    for ox, oy in ((-0.4, -0.5), (0.4, -0.5), (0, -0.5)):
        circle(p, dx + ox * ds * 0.9, dy + oy * ds * 0.9 - (0 if ox == 0 else 0), ds * 0.12, INK)
    px, py = cx + s * 0.02, cy + s * 0.08
    ellipse(p, px, py, s * 0.07, s * 0.03, "#c73636", INK, 1.5)
    path = QPainterPath(QPointF(px - s * 0.055, py))
    path.quadTo(QPointF(px - s * 0.03, py - s * 0.14), QPointF(px, py - s * 0.15))
    path.quadTo(QPointF(px + s * 0.03, py - s * 0.14), QPointF(px + s * 0.055, py))
    path.closeSubpath()
    p.setPen(QPen(INK, 1.5))
    p.setBrush(QColor("#ff4d4d"))
    p.drawPath(path)
    circle(p, px, py - s * 0.17, s * 0.045, "#ffe2c6", INK, 1.5)
    hat = QPainterPath(QPointF(px - s * 0.06, py - s * 0.19))
    hat.quadTo(QPointF(px, py - s * 0.26), QPointF(px + s * 0.06, py - s * 0.19))
    hat.closeSubpath()
    p.setBrush(QColor("#2b2540"))
    p.drawPath(hat)
