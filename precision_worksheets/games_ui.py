"""Five native word-practice mini-games (PySide6), ported from the
reference Word Spin Games web app. Each game is auto-filled from the
child's current 5 tracked words (no typing needed) and logs its score
through db.record_game_score so it shows up on the Games tab and in
the Excel export later. Speech synthesis from the original web version
is intentionally left out to keep the Windows build simple and
reliable - an adult listens and judges "say it out loud" rounds, same
as the original's grown-up-supervised design, just without the optional
voice playback.
"""

from __future__ import annotations

import datetime
import random

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
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


class _GameDialogBase(QDialog):
    def __init__(self, parent, conn, child_id: int, words: list[str], game_key: str):
        super().__init__(parent)
        self.conn = conn
        self.child_id = child_id
        self.words = list(words)
        self.game_key = game_key
        self.setWindowTitle(GAME_LABELS[game_key])
        self.setMinimumSize(560, 460)

        outer = QVBoxLayout(self)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
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
        title = QLabel("\U0001f389 Nice work!")
        title.setObjectName("HeaderLabel")
        layout.addWidget(title)
        for line in lines:
            label = QLabel(line)
            label.setStyleSheet("font-size: 14pt;")
            layout.addWidget(label)

        buttons = QHBoxLayout()
        again_btn = QPushButton("Play again")
        again_btn.setObjectName("AccentButton")
        again_btn.clicked.connect(self._restart)
        buttons.addWidget(again_btn)
        close_btn = QPushButton("Done")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

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
        layout.addWidget(QLabel("Say each word aloud. Tap ✓ or ✗. One minute!", wordWrap=True))

        self.bar = QProgressBar()
        self.bar.setRange(0, 60)
        self.bar.setValue(60)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)

        self.time_label = QLabel("60s")
        layout.addWidget(self.time_label)

        self.word_label = QLabel("")
        self.word_label.setStyleSheet("font-size: 48pt; font-weight: 700;")
        self.word_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.word_label)

        buttons = QHBoxLayout()
        correct_btn = QPushButton("✓ Correct")
        correct_btn.setStyleSheet("background: #2ec4b6; color: white; font-weight: 700;")
        correct_btn.clicked.connect(self._mark_correct)
        buttons.addWidget(correct_btn)
        wrong_btn = QPushButton("✗ Oops")
        wrong_btn.setStyleSheet("background: #ff5d73; color: white; font-weight: 700;")
        wrong_btn.clicked.connect(self._mark_wrong)
        buttons.addWidget(wrong_btn)
        layout.addLayout(buttons)

        self.score_label = QLabel("")
        layout.addWidget(self.score_label)
        layout.addStretch(1)

        self._next_word()
        self._update_score()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _next_word(self) -> None:
        if not self.queue:
            self.queue = random.sample(self.words, len(self.words))
        self.word_label.setText(self.queue.pop())

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
        layout.addWidget(QLabel(f"Round {self.r + 1} / {len(self.rounds)}"))

        self.target_label = QLabel(target)
        self.target_label.setStyleSheet("font-size: 40pt; font-weight: 700; color: #3568b5;")
        self.target_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.target_label)

        self.prompt_label = QLabel("Remember it...")
        self.prompt_label.setObjectName("MutedLabel")
        layout.addWidget(self.prompt_label)

        self.bubble_holder = QWidget()
        self.bubble_grid = QGridLayout(self.bubble_holder)
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
                f"background: {color}; color: white; font-size: 14pt; font-weight: 700; "
                "border-radius: 18px; padding: 18px;"
            )
            btn.clicked.connect(lambda _checked=False, w=word, b=btn: self._pop(w, target, b))
            self.bubble_grid.addWidget(btn, i // 3, i % 3)

    def _pop(self, word: str, target: str, btn: QPushButton) -> None:
        if word == target:
            if not self.missed_this_round:
                self.score += 1
            self.r += 1
            self._next_round()
        else:
            self.missed_this_round = True
            btn.setStyleSheet(btn.styleSheet() + "border: 3px solid #a03030;")


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
        layout.addWidget(QLabel("Flip two cards. Say the word out loud every time!", wordWrap=True))

        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        layout.addWidget(grid_holder)
        layout.addStretch(1)

        self.cards: list[QPushButton] = []
        for i, word in enumerate(cards):
            btn = QPushButton("?")
            btn.setFixedSize(90, 90)
            btn.setStyleSheet("font-size: 14pt; font-weight: 700;")
            btn.clicked.connect(lambda _checked=False, w=word, b=btn: self._flip(w, b))
            grid.addWidget(btn, i // 5, i % 5)
            self.cards.append(btn)

    def _flip(self, word: str, btn: QPushButton) -> None:
        if self.lock or btn.text() != "?" or not btn.isEnabled():
            return
        btn.setText(word)

        if self.first_btn is None:
            self.first_btn = btn
            self.first_word = word
            return

        self.moves += 1
        if self.first_word == word:
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
        layout.addWidget(QLabel(f"Word {self.r + 1} / {len(self.rounds)}"))

        self.word_label = QLabel(word)
        self.word_label.setStyleSheet("font-size: 40pt; font-weight: 700;")
        self.word_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.word_label)

        self.msg_label = QLabel("Look carefully...")
        self.msg_label.setObjectName("MutedLabel")
        layout.addWidget(self.msg_label)

        self.btn_row = QHBoxLayout()
        layout.addLayout(self.btn_row)
        layout.addStretch(1)

        QTimer.singleShot(2000, lambda: self._hide_word(word))

    def _hide_word(self, word: str) -> None:
        self.word_label.setText("❓")
        self.msg_label.setText("Say the word!")
        reveal_btn = QPushButton("Show me")
        reveal_btn.clicked.connect(lambda: self._reveal(word))
        self.btn_row.addWidget(reveal_btn)

    def _reveal(self, word: str) -> None:
        self.word_label.setText(word)
        self.msg_label.setText("Did they get it right?")
        _clear_layout(self.btn_row)

        yes_btn = QPushButton("✓ Yes")
        yes_btn.setStyleSheet("background: #2ec4b6; color: white; font-weight: 700;")
        yes_btn.clicked.connect(lambda: self._answer(True))
        self.btn_row.addWidget(yes_btn)

        no_btn = QPushButton("✗ Not yet")
        no_btn.setStyleSheet("background: #ff5d73; color: white; font-weight: 700;")
        no_btn.clicked.connect(lambda: self._answer(False))
        self.btn_row.addWidget(no_btn)

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
            self._record_and_finish(self.oops, [f"\U0001f524 {len(self.rounds)} words unscrambled", f"\U0001f605 {self.oops} wrong taps"])
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
        layout.addWidget(QLabel(f"Word {self.r + 1} / {len(self.rounds)}"))

        self.slots_row = QHBoxLayout()
        self.slot_labels: list[QLabel] = []
        for _ in letters:
            lbl = QLabel("")
            lbl.setFixedSize(60, 70)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 28pt; font-weight: 700; border-bottom: 4px solid #6b7280;")
            self.slots_row.addWidget(lbl)
            self.slot_labels.append(lbl)
        layout.addLayout(self.slots_row)

        self.tiles_row = QHBoxLayout()
        layout.addLayout(self.tiles_row)

        self.msg_label = QLabel("Tap the letters in order")
        self.msg_label.setObjectName("MutedLabel")
        layout.addWidget(self.msg_label)
        layout.addStretch(1)

        self.tile_buttons: list[QPushButton] = []
        for ch in tiles:
            btn = QPushButton(ch)
            btn.setFixedSize(60, 60)
            btn.setStyleSheet("font-size: 20pt; font-weight: 700;")
            btn.clicked.connect(lambda _checked=False, c=ch, b=btn: self._tap(c, b))
            self.tiles_row.addWidget(btn)
            self.tile_buttons.append(btn)

    def _tap(self, ch: str, btn: QPushButton) -> None:
        if not btn.isEnabled():
            return
        if ch == self.letters[self.pos]:
            self.slot_labels[self.pos].setText(ch)
            btn.setEnabled(False)
            self.pos += 1
            if self.pos == len(self.letters):
                self.msg_label.setText(f"Now say it out loud! {self.target_word}")
                next_btn = QPushButton("Next →")
                next_btn.setObjectName("AccentButton")
                next_btn.clicked.connect(self._advance)
                self.slots_row.addWidget(next_btn)
        else:
            self.oops += 1
            btn.setStyleSheet(btn.styleSheet() + "border: 3px solid #a03030;")

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
        layout.addLayout(self.cards_layout)
        layout.addStretch(1)

        self._refresh()

    def _refresh(self) -> None:
        _clear_layout(self.cards_layout)
        scores = best_scores(self.conn, self.child_id)

        for key, title, metric, _lower in GAME_DEFS:
            box = QGroupBox(title)
            row = QHBoxLayout(box)

            if key in scores:
                best, count = scores[key]
                best_text = f"{best:g}{metric}"
                info = QLabel(f"Best: {best_text}   ·   Played {count}×")
            else:
                info = QLabel("Not played yet")
            info.setObjectName("MutedLabel")
            row.addWidget(info, 1)

            play_btn = QPushButton("Play")
            play_btn.setObjectName("AccentButton")
            play_btn.clicked.connect(lambda _checked=False, k=key: self._play(k))
            row.addWidget(play_btn)

            self.cards_layout.addWidget(box)

    def _play(self, key: str) -> None:
        if len(self.words) < 2:
            return
        dialog_cls = DIALOG_CLASSES[key]
        dlg = dialog_cls(self, self.conn, self.child_id, self.words)
        dlg.exec()
        self._refresh()
