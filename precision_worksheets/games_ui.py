"""The Games tab on a child's page, and the score bookkeeping shared with
the Word Arcade (see the arcade package for the games themselves).

Each game is auto-filled from the child's current practice words (no
typing needed) and logs its score through db.record_game_score, so it
shows up on the hub tiles and in the Excel export.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import db

# (key, title, metric suffix, lower_is_better) - the first five keys are
# the original games, so scores saved before the arcade redesign still
# count as each game's history.
GAME_DEFS = [
    ("flash", "Rocket Blitz", "/min", False),
    ("pop", "Bubble Pop", "/8", False),
    ("memory", "Memory Match", " moves", True),
    ("peek", "Peekaboo Owl", "/10", False),
    ("scramble", "Letter Train", " oops", True),
    ("whack", "Whack-a-Word", " bonks", False),
    ("catch", "Word Catcher", " caught", False),
]
GAME_LABELS = {key: title for key, title, _metric, _lower in GAME_DEFS}
GAME_METRICS = {key: metric for key, _title, metric, _lower in GAME_DEFS}
GAME_LOWER_IS_BETTER = {key: lower for key, _title, _metric, lower in GAME_DEFS}


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


def open_arcade(parent, conn, child_id: int, child_name: str, words: list[str], start_game: str | None = None) -> None:
    from .arcade.arcade import ArcadeWindow

    if len([w for w in words if w.strip()]) < 2:
        return
    win = ArcadeWindow(parent, conn, child_id, child_name, words, start_game=start_game)
    win.exec()


class GamesTab(QWidget):
    """A big 'open the arcade' button plus the arcade's game tiles right
    there in the tab - one click on a tile starts that game."""

    def __init__(self, parent_screen, conn, child_id: int, words_provider: Callable[[], list[str]] | list[str],
                 child_name: str = ""):
        super().__init__()
        from .arcade.arcade import HubCanvas

        self.parent_screen = parent_screen
        self.conn = conn
        self.child_id = child_id
        self.child_name = child_name
        self.words_provider = words_provider if callable(words_provider) else (lambda w=list(words_provider): w)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        top = QHBoxLayout()
        intro = QLabel("Games use this week's words automatically. Scores are saved for each child.")
        intro.setObjectName("MutedLabel")
        intro.setWordWrap(True)
        top.addWidget(intro, 1)
        open_btn = QPushButton("\U0001f3ae  Open the Word Arcade")
        open_btn.setObjectName("ArcadeButton")
        open_btn.clicked.connect(lambda: self._play(None))
        top.addWidget(open_btn)
        layout.addLayout(top)

        self.hub = HubCanvas(child_name, self.words_provider, lambda: best_scores(self.conn, self.child_id),
                             self._play, compact=True)
        layout.addWidget(self.hub, 1)

    def _play(self, key: str | None) -> None:
        open_arcade(self, self.conn, self.child_id, self.child_name, self.words_provider(), start_game=key)
        self.hub.refresh()
