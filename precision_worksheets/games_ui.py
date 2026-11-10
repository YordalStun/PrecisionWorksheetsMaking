"""Five native word-practice mini-games (PySide6), ported from the
reference Word Spin Games web app. Each game is auto-filled from the
child's current 5 tracked words (no typing needed) and logs its score
through db.record_game_score so it shows up on the Games tab and in
the Excel export later. Speech synthesis from the original web version
is intentionally left out to keep the Windows build simple and
reliable - an adult listens and judges "say it out loud" rounds, same
as the original's grown-up-supervised design, just without the optional
voice playback.

Visual style: each game gets its own bright gradient theme and big,
rounded, colourful controls (game_chrome.py) rather than plain default
widgets, plus a confetti burst on finishing - the point is to feel like
a game, not a form.
"""

from __future__ import annotations

import datetime
import random

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import db
from .game_chrome import GAME_THEMES, ConfettiBurst, apply_theme, big_label_style, flash_button

# (key, title, metric suffix, lower_is_better)
GAME_DEFS = [
    ("flash", "⚡ Flash Blitz", "/min", False),
    ("pop", "\U0001fae7 Pop the Word", "/8", False),
    ("memory", "\U0001f0cf Memory Match", " moves", True),
    ("peek", "\U0001f440 Now You See It", "/10", False),
    ("scramble", "\U0001f524 Letter Scramble", " oops", True),
]
GAME_LABELS = {key: title for key, title, _metric, _lower in GAME_DEFS}
GAME_METRICS = {key: metric for key, _title, metric, _lower in GAME_DEFS}
GAME_LOWER_IS_BETTER = {key: lower for key, _title, _metric, lower in GAME_DEFS}

BUBBLE_COLORS = ["#7c4dff", "#ffb703", "#2ec4b6", "#ff5d73", "#35b6ff"]
CORRECT_COLOR = "#2ec97a"
WRONG_COLOR = "#e8435c"


def best_scores(conn, child_id: int) -> dict[str, tuple[float, int]]:
    """Returns {game_key: (best_score, play_count)} from the recorded history."""
    rows = db.get_game_scores(conn, child_id)
    out: dict[str, tuple[float, int]] = {}
    for row in rows:
        key = row["game"]
        score = row["score"]
        if key not in out:
            out[key] = (score, 1)
        else:
            best, count = out[key]
            lower_better = GAME_LOWER_IS_BETTER.get(key, False)
            better = score < best if lower_better else score > best
            out[key] = (score if better else best, count + 1)
    return out


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


def _pop_in(widget: QWidget, duration: int = 260) -> QPropertyAnimation:
    """A quick fade/scale-in so a new word or round doesn't just snap into
    place. Returns the animation; callers must keep a reference to it
    (e.g. self._anim = ...) for the duration, or Python may garbage
    collect it mid-flight."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    return anim


class _GameDialogBase(QDialog):
    def __init__(self, parent, conn, child_id: int, words: list[str], game_key: str):
        super().__init__(parent)
        self.conn = conn
        self.child_id = child_id
        self.words = list(words)
        self.game_key = game_key
        self.setWindowTitle(GAME_LABELS[game_key])
        self.setMinimumSize(600, 520)
        self.theme = apply_theme(self, game_key)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        self.body = QWidget()
        self.body.setObjectName("GameBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setSpacing(16)
        outer.addWidget(self.body, 1)

    def _reset_body(self) -> QVBoxLayout:
        _clear_layout(self.body_layout)
        return self.body_layout

    def _record_and_finish(self, score: float, lines: list[str]) -> None:
        date_str = datetime.date.today().strftime("%d/%m/%Y")
        db.record_game_score(self.conn, self.child_id, self.game_key, date_str, score, GAME_METRICS[self.game_key])
        self._show_finish(lines)

    def _show_finish(self, lines: list[str]) -> None:
        layout = self._reset_body()
        layout.addStretch(1)

        title = QLabel("\U0001f389 Nice work!")
        title.setStyleSheet(big_label_style(self.theme, 34))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        for line in lines:
            label = QLabel(line)
            label.setStyleSheet(f"font-size: 15pt; font-weight: 600; color: {self.theme['ink']};")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        again_btn = QPushButton("\U0001f504 Play again")
        again_btn.setObjectName("GameAccent")
        again_btn.clicked.connect(self._restart)
        buttons.addWidget(again_btn)
        close_btn = QPushButton("Done")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

        self._confetti = ConfettiBurst(self, self.theme["confetti"])

    def _restart(self) -> None:
        self._start()

    def _start(self) -> None:
        raise NotImplementedError


class FlashBlitzDialog(_GameDialogBase):
    def __init__(self, parent, conn, child_id: int, words: list[str]):
        super().__init__(parent, conn, child_id, words, "flash")
        self._start()

    def _start(self) -> None:
        self.ok = 0
        self.er = 0
        self.time_left = 60
        self.queue: list[str] = []

        layout = self._reset_body()
        intro = QLabel("Say each word aloud. Tap ✓ or ✗. One minute!")
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignCenter)
        intro.setStyleSheet("font-size: 12pt; font-weight: 600;")
        layout.addWidget(intro)

        self.bar = QProgressBar()
        self.bar.setRange(0, 60)
        self.bar.setValue(60)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(16)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: rgba(255,255,255,0.5); border-radius: 8px; }}"
            f"QProgressBar::chunk {{ background: {self.theme['accent']}; border-radius: 8px; }}"
        )
        layout.addWidget(self.bar)

        self.time_label = QLabel("60s")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setStyleSheet("font-size: 13pt; font-weight: 700;")
        layout.addWidget(self.time_label)

        self.word_label = QLabel("")
        self.word_label.setStyleSheet(big_label_style(self.theme, 50))
        self.word_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.word_label, 1)

        buttons = QHBoxLayout()
        correct_btn = QPushButton("✓ Correct")
        flash_button(correct_btn, CORRECT_COLOR)
        correct_btn.clicked.connect(self._mark_correct)
        buttons.addWidget(correct_btn)
        wrong_btn = QPushButton("✗ Oops")
        flash_button(wrong_btn, WRONG_COLOR)
        wrong_btn.clicked.connect(self._mark_wrong)
        buttons.addWidget(wrong_btn)
        layout.addLayout(buttons)

        self.score_label = QLabel("")
        self.score_label.setAlignment(Qt.AlignCenter)
        self.score_label.setStyleSheet("font-size: 13pt; font-weight: 700;")
        layout.addWidget(self.score_label)

        self._next_word()
        self._update_score()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _next_word(self) -> None:
        if not self.queue:
            self.queue = random.sample(self.words, len(self.words))
        self.word_label.setText(self.queue.pop())
        self._anim = _pop_in(self.word_label)

    def _update_score(self) -> None:
        self.score_label.setText(f"✓ {self.ok}   ✗ {self.er}")

    def _mark_correct(self) -> None:
        self.ok += 1
        self._update_score()
        self._next_word()

    def _mark_wrong(self) -> None:
        self.er += 1
        self._update_score()
        self._next_word()

    def _tick(self) -> None:
        self.time_left -= 1
        self.time_label.setText(f"{self.time_left}s")
        self.bar.setValue(max(self.time_left, 0))
        if self.time_left <= 0:
            self.timer.stop()
            self._record_and_finish(self.ok, [f"✓ {self.ok} correct in a minute", f"✗ {self.er} errors"])


class PopTheWordDialog(_GameDialogBase):
    def __init__(self, parent, conn, child_id: int, words: list[str]):
        super().__init__(parent, conn, child_id, words, "pop")
        self._start()

    def _start(self) -> None:
        self.rounds = random.sample(self.words * 2, min(8, len(self.words) * 2))
        self.r = 0
        self.score = 0
        self._next_round()

    def _next_round(self) -> None:
        if self.r >= len(self.rounds):
            self._record_and_finish(self.score, [f"\U0001fae7 {self.score} / {len(self.rounds)} found first try"])
            return

        target = self.rounds[self.r]
        self.missed_this_round = False

        layout = self._reset_body()
        round_lbl = QLabel(f"Round {self.r + 1} / {len(self.rounds)}")
        round_lbl.setAlignment(Qt.AlignCenter)
        round_lbl.setStyleSheet("font-size: 12pt; font-weight: 700;")
        layout.addWidget(round_lbl)

        self.target_label = QLabel(target)
        self.target_label.setStyleSheet(big_label_style(self.theme, 44))
        self.target_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.target_label)
        self._anim = _pop_in(self.target_label)

        self.prompt_label = QLabel("Remember it...")
        self.prompt_label.setAlignment(Qt.AlignCenter)
        self.prompt_label.setStyleSheet(f"color: {self.theme['ink']}; font-size: 11pt;")
        layout.addWidget(self.prompt_label)

        self.bubble_holder = QWidget()
        self.bubble_grid = QGridLayout(self.bubble_holder)
        self.bubble_grid.setSpacing(14)
        layout.addWidget(self.bubble_holder)
        layout.addStretch(1)

        QTimer.singleShot(1300, lambda: self._reveal_bubbles(target))

    def _reveal_bubbles(self, target: str) -> None:
        self.target_label.setText("❓")
        self.prompt_label.setText("Tap the word you saw!")

        shuffled = random.sample(self.words, len(self.words))
        for i, word in enumerate(shuffled):
            btn = QPushButton(word)
            color = BUBBLE_COLORS[i % len(BUBBLE_COLORS)]
            btn.setStyleSheet(
                f"background: {color}; color: white; font-size: 14pt; font-weight: 800; "
                "border: none; border-radius: 22px; padding: 22px;"
            )
            btn.clicked.connect(lambda _checked=False, w=word, b=btn: self._pop(w, target, b))
            self.bubble_grid.addWidget(btn, i // 3, i % 3)
            _pop_in(btn, 220)

    def _pop(self, word: str, target: str, btn: QPushButton) -> None:
        if word == target:
            if not self.missed_this_round:
                self.score += 1
            self.r += 1
            self._next_round()
        else:
            self.missed_this_round = True
            btn.setStyleSheet(btn.styleSheet() + f"border: 4px solid {WRONG_COLOR};")


class MemoryMatchDialog(_GameDialogBase):
    def __init__(self, parent, conn, child_id: int, words: list[str]):
        super().__init__(parent, conn, child_id, words, "memory")
        self._start()

    def _start(self) -> None:
        self.moves = 0
        self.pairs = 0
        self.first_btn: QPushButton | None = None
        self.first_word: str | None = None
        self.lock = False

        cards = self.words * 2
        random.shuffle(cards)

        layout = self._reset_body()
        intro = QLabel("Flip two cards. Say the word out loud every time!")
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignCenter)
        intro.setStyleSheet("font-size: 12pt; font-weight: 600;")
        layout.addWidget(intro)

        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setSpacing(10)
        layout.addWidget(grid_holder)
        layout.addStretch(1)

        self._facedown_style = (
            f"background: {self.theme['accent']}; color: white; font-size: 20pt; font-weight: 800; "
            "border: none; border-radius: 14px;"
        )
        self._faceup_style = (
            f"background: white; color: {self.theme['ink']}; font-size: 12pt; font-weight: 800; "
            "border: 2px solid rgba(0,0,0,0.15); border-radius: 14px;"
        )
        self._matched_style = (
            f"background: {CORRECT_COLOR}; color: white; font-size: 12pt; font-weight: 800; "
            "border: none; border-radius: 14px;"
        )

        self.cards: list[QPushButton] = []
        for i, word in enumerate(cards):
            btn = QPushButton("?")
            btn.setFixedSize(96, 96)
            btn.setStyleSheet(self._facedown_style)
            btn.clicked.connect(lambda _checked=False, w=word, b=btn: self._flip(w, b))
            grid.addWidget(btn, i // 5, i % 5)
            self.cards.append(btn)

    def _flip(self, word: str, btn: QPushButton) -> None:
        if self.lock or btn.text() != "?" or not btn.isEnabled():
            return
        btn.setText(word)
        btn.setStyleSheet(self._faceup_style)

        if self.first_btn is None:
            self.first_btn = btn
            self.first_word = word
            return

        self.moves += 1
        if self.first_word == word:
            self.first_btn.setStyleSheet(self._matched_style)
            btn.setStyleSheet(self._matched_style)
            self.first_btn.setEnabled(False)
            btn.setEnabled(False)
            self.first_btn = None
            self.first_word = None
            self.pairs += 1
            if self.pairs == len(self.words):
                self._record_and_finish(self.moves, [f"\U0001f0cf Matched all {self.pairs} pairs in {self.moves} moves"])
        else:
            self.lock = True
            other = self.first_btn
            self.first_btn = None
            self.first_word = None
            QTimer.singleShot(900, lambda: self._hide_pair(other, btn))

    def _hide_pair(self, a: QPushButton, b: QPushButton) -> None:
        a.setText("?")
        b.setText("?")
        a.setStyleSheet(self._facedown_style)
        b.setStyleSheet(self._facedown_style)
        self.lock = False


class PeekDialog(_GameDialogBase):
    def __init__(self, parent, conn, child_id: int, words: list[str]):
        super().__init__(parent, conn, child_id, words, "peek")
        self._start()

    def _start(self) -> None:
        self.rounds = random.sample(self.words * 2, min(10, len(self.words) * 2))
        self.r = 0
        self.score = 0
        self._next_round()

    def _next_round(self) -> None:
        if self.r >= len(self.rounds):
            self._record_and_finish(self.score, [f"\U0001f440 {self.score} / {len(self.rounds)} remembered"])
            return

        word = self.rounds[self.r]
        layout = self._reset_body()
        round_lbl = QLabel(f"Word {self.r + 1} / {len(self.rounds)}")
        round_lbl.setAlignment(Qt.AlignCenter)
        round_lbl.setStyleSheet("font-size: 12pt; font-weight: 700;")
        layout.addWidget(round_lbl)

        self.word_label = QLabel(word)
        self.word_label.setStyleSheet(big_label_style(self.theme, 44))
        self.word_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.word_label, 1)
        self._anim = _pop_in(self.word_label)

        self.msg_label = QLabel("Look carefully...")
        self.msg_label.setAlignment(Qt.AlignCenter)
        self.msg_label.setStyleSheet(f"color: {self.theme['ink']}; font-size: 11pt;")
        layout.addWidget(self.msg_label)

        self.btn_row = QHBoxLayout()
        self.btn_row.addStretch(1)
        layout.addLayout(self.btn_row)
        layout.addStretch(1)

        QTimer.singleShot(2000, lambda: self._hide_word(word))

    def _hide_word(self, word: str) -> None:
        self.word_label.setText("❓")
        self.msg_label.setText("Say the word!")
        reveal_btn = QPushButton("Show me")
        reveal_btn.setObjectName("GameAccent")
        reveal_btn.clicked.connect(lambda: self._reveal(word))
        self.btn_row.insertWidget(0, reveal_btn)

    def _reveal(self, word: str) -> None:
        self.word_label.setText(word)
        self.msg_label.setText("Did they get it right?")
        while self.btn_row.count() > 1:
            item = self.btn_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        yes_btn = QPushButton("✓ Yes")
        flash_button(yes_btn, CORRECT_COLOR)
        yes_btn.clicked.connect(lambda: self._answer(True))
        self.btn_row.insertWidget(0, yes_btn)

        no_btn = QPushButton("✗ Not yet")
        flash_button(no_btn, WRONG_COLOR)
        no_btn.clicked.connect(lambda: self._answer(False))
        self.btn_row.insertWidget(1, no_btn)

    def _answer(self, correct: bool) -> None:
        if correct:
            self.score += 1
        self.r += 1
        self._next_round()


class LetterScrambleDialog(_GameDialogBase):
    def __init__(self, parent, conn, child_id: int, words: list[str]):
        super().__init__(parent, conn, child_id, words, "scramble")
        self._start()

    def _start(self) -> None:
        self.rounds = random.sample(self.words, len(self.words))
        self.r = 0
        self.oops = 0
        self._next_round()

    def _next_round(self) -> None:
        if self.r >= len(self.rounds):
            self._record_and_finish(
                self.oops, [f"\U0001f524 {len(self.rounds)} words unscrambled", f"\U0001f605 {self.oops} wrong taps"]
            )
            return

        word = self.rounds[self.r]
        letters = list(word)
        tiles = letters[:]
        if len(letters) > 1:
            for _ in range(20):
                random.shuffle(tiles)
                if "".join(tiles) != word:
                    break

        self.target_word = word
        self.letters = letters
        self.pos = 0

        layout = self._reset_body()
        round_lbl = QLabel(f"Word {self.r + 1} / {len(self.rounds)}")
        round_lbl.setAlignment(Qt.AlignCenter)
        round_lbl.setStyleSheet("font-size: 12pt; font-weight: 700;")
        layout.addWidget(round_lbl)

        self.slots_row = QHBoxLayout()
        self.slots_row.addStretch(1)
        self.slot_labels: list[QLabel] = []
        for _ in letters:
            lbl = QLabel("")
            lbl.setFixedSize(60, 70)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"font-size: 28pt; font-weight: 800; color: {self.theme['ink']}; "
                f"border-bottom: 5px solid {self.theme['accent']};"
            )
            self.slots_row.addWidget(lbl)
            self.slot_labels.append(lbl)
        self.slots_row.addStretch(1)
        layout.addLayout(self.slots_row)

        self.tiles_row = QHBoxLayout()
        self.tiles_row.addStretch(1)
        layout.addLayout(self.tiles_row)
        layout.addStretch(1)

        self.msg_label = QLabel("Tap the letters in order")
        self.msg_label.setAlignment(Qt.AlignCenter)
        self.msg_label.setStyleSheet(f"color: {self.theme['ink']}; font-size: 11pt;")
        layout.addWidget(self.msg_label)

        self.tile_buttons: list[QPushButton] = []
        for ch in tiles:
            btn = QPushButton(ch.upper())
            btn.setFixedSize(64, 64)
            btn.setStyleSheet(
                f"background: {self.theme['accent']}; color: white; font-size: 20pt; font-weight: 800; "
                "border: none; border-radius: 14px;"
            )
            btn.clicked.connect(lambda _checked=False, c=ch, b=btn: self._tap(c, b))
            self.tiles_row.addWidget(btn)
            self.tile_buttons.append(btn)
        self.tiles_row.addStretch(1)

    def _tap(self, ch: str, btn: QPushButton) -> None:
        if not btn.isEnabled():
            return
        if ch == self.letters[self.pos]:
            self.slot_labels[self.pos].setText(ch)
            btn.setEnabled(False)
            btn.setStyleSheet(
                f"background: {CORRECT_COLOR}; color: white; font-size: 20pt; font-weight: 800; "
                "border: none; border-radius: 14px;"
            )
            self.pos += 1
            if self.pos == len(self.letters):
                self.msg_label.setText(f"Now say it out loud! {self.target_word}")
                next_btn = QPushButton("Next →")
                next_btn.setObjectName("GameAccent")
                next_btn.clicked.connect(self._advance)
                self.slots_row.insertWidget(self.slots_row.count() - 1, next_btn)
        else:
            self.oops += 1
            flash_button(btn, WRONG_COLOR)
            QTimer.singleShot(
                220,
                lambda b=btn: b.setStyleSheet(
                    f"background: {self.theme['accent']}; color: white; font-size: 20pt; font-weight: 800; "
                    "border: none; border-radius: 14px;"
                ),
            )

    def _advance(self) -> None:
        self.r += 1
        self._next_round()


DIALOG_CLASSES = {
    "flash": FlashBlitzDialog,
    "pop": PopTheWordDialog,
    "memory": MemoryMatchDialog,
    "peek": PeekDialog,
    "scramble": LetterScrambleDialog,
}


class GamesTab(QWidget):
    def __init__(self, parent_screen, conn, child_id: int, words: list[str]):
        super().__init__()
        self.parent_screen = parent_screen
        self.conn = conn
        self.child_id = child_id
        self.words = words

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        intro = QLabel(
            "Games use this week's 5 words automatically - no typing needed. "
            "Scores are saved and logged for each child."
        )
        intro.setObjectName("MutedLabel")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(10)
        layout.addLayout(self.cards_layout)
        layout.addStretch(1)

        self._refresh()

    def _refresh(self) -> None:
        _clear_layout(self.cards_layout)
        scores = best_scores(self.conn, self.child_id)

        for key, title, metric, _lower in GAME_DEFS:
            theme = GAME_THEMES[key]
            card = QGroupBox(title)
            card.setStyleSheet(
                f"""
                QGroupBox {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {theme['bg_top']}, stop:1 {theme['bg_bottom']});
                    border: none; border-radius: 14px;
                    margin-top: 14px; padding: 14px 12px 12px 12px;
                    font-weight: 700; color: {theme['ink']};
                }}
                QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {theme['ink']}; }}
                """
            )
            row = QHBoxLayout(card)

            if key in scores:
                best, count = scores[key]
                best_text = f"{best:g}{metric}"
                info = QLabel(f"Best: {best_text}   ·   Played {count}×")
            else:
                info = QLabel("Not played yet")
            info.setStyleSheet(f"color: {theme['ink']}; background: transparent;")
            row.addWidget(info, 1)

            play_btn = QPushButton("▶ Play")
            play_btn.setStyleSheet(
                f"background: white; color: {theme['ink']}; border: none; border-radius: 10px; "
                "padding: 10px 20px; font-weight: 800;"
            )
            play_btn.clicked.connect(lambda _checked=False, k=key: self._play(k))
            row.addWidget(play_btn)

            self.cards_layout.addWidget(card)

    def _play(self, key: str) -> None:
        if len(self.words) < 2:
            return
        dialog_cls = DIALOG_CLASSES[key]
        dlg = dialog_cls(self, self.conn, self.child_id, self.words)
        dlg.exec()
        self._refresh()
