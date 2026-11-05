"""SQLite-backed storage for per-child word tracking.

One child has one row per word in their *current* tier in `word_state`
(seeded all at once when the child is added, or when they graduate to the
next tier) - words from tiers before their current one aren't stored
individually, they're assumed fully mastered (see `earlier_tier_known_words`).
"""

from __future__ import annotations

import os
import random
import sqlite3
from datetime import datetime

from .data.word_lists import TIERS, TIERS_BY_KEY, tier_index
from .tracking import STATUS_KNOWN, STATUS_LEARNING, WordState, apply_result, pick_known_words, pick_practice_words

DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), "Documents", "PrecisionWorksheets", "precision_tracking.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS children (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    year_group TEXT,
    current_tier TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_sheet_words TEXT,
    last_sheet_date TEXT
);

CREATE TABLE IF NOT EXISTS word_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    tier TEXT NOT NULL,
    word TEXT NOT NULL,
    status TEXT NOT NULL,
    correct_streak INTEGER NOT NULL DEFAULT 0,
    times_seen INTEGER NOT NULL DEFAULT 0,
    times_correct INTEGER NOT NULL DEFAULT 0,
    last_result TEXT,
    last_practiced TEXT,
    UNIQUE(child_id, tier, word)
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    tier TEXT NOT NULL,
    time_seconds INTEGER,
    correct_count INTEGER,
    error_count INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    word TEXT NOT NULL,
    correct INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS game_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    game TEXT NOT NULL,
    date TEXT NOT NULL,
    score REAL NOT NULL,
    metric TEXT,
    created_at TEXT NOT NULL
);
"""


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ----------------------------------------------------------------------
# Children
# ----------------------------------------------------------------------
def add_child(conn: sqlite3.Connection, name: str, year_group: str, tier_key: str, known_words: set[str]) -> int:
    """Create a child and seed word_state for every word in their
    starting tier, based on which ones they already know."""
    name = name.strip()
    if not name:
        raise ValueError("Please enter the child's name.")
    if tier_key not in TIERS_BY_KEY:
        raise ValueError(f"Unknown tier: {tier_key}")

    cur = conn.execute(
        "INSERT INTO children (name, year_group, current_tier, created_at) VALUES (?, ?, ?, ?)",
        (name, year_group.strip(), tier_key, _now_iso()),
    )
    child_id = cur.lastrowid
    _seed_tier(conn, child_id, tier_key, known_words)
    conn.commit()
    return child_id


def _seed_tier(conn: sqlite3.Connection, child_id: int, tier_key: str, known_words: set[str]) -> None:
    tier = TIERS_BY_KEY[tier_key]
    rows = []
    for word in tier.words:
        if word in known_words:
            rows.append((child_id, tier_key, word, STATUS_KNOWN, 3, 0, 0, None, None))
        else:
            rows.append((child_id, tier_key, word, STATUS_LEARNING, 0, 0, 0, None, None))
    conn.executemany(
        """INSERT OR IGNORE INTO word_state
           (child_id, tier, word, status, correct_streak, times_seen, times_correct, last_result, last_practiced)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )


def list_children(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM children ORDER BY name COLLATE NOCASE").fetchall()


def get_child(conn: sqlite3.Connection, child_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()


def delete_child(conn: sqlite3.Connection, child_id: int) -> None:
    conn.execute("DELETE FROM children WHERE id = ?", (child_id,))
    conn.commit()


def rename_child(conn: sqlite3.Connection, child_id: int, name: str, year_group: str) -> None:
    conn.execute(
        "UPDATE children SET name = ?, year_group = ? WHERE id = ?",
        (name.strip(), year_group.strip(), child_id),
    )
    conn.commit()


# ----------------------------------------------------------------------
# Word state
# ----------------------------------------------------------------------
def get_word_states(conn: sqlite3.Connection, child_id: int, tier_key: str) -> list[WordState]:
    rows = conn.execute(
        "SELECT word, status, correct_streak, times_seen, times_correct FROM word_state "
        "WHERE child_id = ? AND tier = ?",
        (child_id, tier_key),
    ).fetchall()
    by_word = {
        r["word"]: WordState(r["word"], r["status"], r["correct_streak"], r["times_seen"], r["times_correct"])
        for r in rows
    }
    tier = TIERS_BY_KEY[tier_key]
    return [by_word[w] for w in tier.words if w in by_word]


def known_words(conn: sqlite3.Connection, child_id: int, tier_key: str) -> list[str]:
    return [s.word for s in get_word_states(conn, child_id, tier_key) if s.status == STATUS_KNOWN]


def learning_words(conn: sqlite3.Connection, child_id: int, tier_key: str) -> list[WordState]:
    return [s for s in get_word_states(conn, child_id, tier_key) if s.status == STATUS_LEARNING]


def earlier_tier_known_words(tier_key: str) -> list[str]:
    """All words from every tier before `tier_key` - a child on a given
    tier is assumed to have already mastered every tier before it."""
    idx = tier_index(tier_key)
    words: list[str] = []
    for t in TIERS[:idx]:
        words.extend(t.words)
    return words


def all_known_words(conn: sqlite3.Connection, child_id: int, tier_key: str) -> list[str]:
    """Every word available for the '2 known words' slot: earlier tiers
    (assumed complete) plus mastered words in the current tier."""
    return earlier_tier_known_words(tier_key) + known_words(conn, child_id, tier_key)


def choose_session_words(conn: sqlite3.Connection, child_id: int, rng: random.Random | None = None) -> list[str]:
    """The 5 words for this child's next sheet: 3 to practise (struggling
    words first, then the next new ones in tier order) + 2 random known
    words."""
    rng = rng or random.Random()
    child = get_child(conn, child_id)
    if child is None:
        raise ValueError(f"No such child: {child_id}")
    tier_key = child["current_tier"]
    practice = pick_practice_words(learning_words(conn, child_id, tier_key))
    known_pick = pick_known_words(all_known_words(conn, child_id, tier_key), rng)
    return practice + known_pick


def set_last_sheet(conn: sqlite3.Connection, child_id: int, words: list[str], date_str: str) -> None:
    """Remember exactly which 5 words were used for this child's most
    recently generated sheet, so recording results afterwards logs the
    words that were actually printed rather than re-picking a fresh
    (possibly different) random set."""
    conn.execute(
        "UPDATE children SET last_sheet_words = ?, last_sheet_date = ? WHERE id = ?",
        (",".join(words), date_str, child_id),
    )
    conn.commit()


def get_last_sheet_words(conn: sqlite3.Connection, child_id: int) -> list[str] | None:
    child = get_child(conn, child_id)
    if child is None or not child["last_sheet_words"]:
        return None
    return child["last_sheet_words"].split(",")


# ----------------------------------------------------------------------
# Sessions (weekly score entry)
# ----------------------------------------------------------------------
def record_session(
    conn: sqlite3.Connection,
    child_id: int,
    date_str: str,
    word_results: list[tuple[str, bool]],
    time_seconds: int | None = None,
    correct_count: int | None = None,
    error_count: int | None = None,
    notes: str = "",
) -> int:
    """Log one week's results and update word mastery state accordingly -
    may also advance the child to the next tier if every word in their
    current one is now known."""
    child = get_child(conn, child_id)
    if child is None:
        raise ValueError(f"No such child: {child_id}")
    tier_key = child["current_tier"]

    cur = conn.execute(
        "INSERT INTO sessions (child_id, date, tier, time_seconds, correct_count, error_count, notes, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (child_id, date_str, tier_key, time_seconds, correct_count, error_count, notes, _now_iso()),
    )
    session_id = cur.lastrowid

    for word, correct in word_results:
        conn.execute(
            "INSERT INTO session_words (session_id, word, correct) VALUES (?, ?, ?)",
            (session_id, word, 1 if correct else 0),
        )
        row = conn.execute(
            "SELECT status, correct_streak, times_seen, times_correct FROM word_state "
            "WHERE child_id = ? AND tier = ? AND word = ?",
            (child_id, tier_key, word),
        ).fetchone()
        if row is None:
            # A known word from an earlier tier (or otherwise untracked) -
            # nothing to update.
            continue
        state = WordState(word, row["status"], row["correct_streak"], row["times_seen"], row["times_correct"])
        new_state = apply_result(state, correct)
        conn.execute(
            "UPDATE word_state SET status = ?, correct_streak = ?, times_seen = ?, times_correct = ?, "
            "last_result = ?, last_practiced = ? WHERE child_id = ? AND tier = ? AND word = ?",
            (
                new_state.status, new_state.correct_streak, new_state.times_seen, new_state.times_correct,
                "correct" if correct else "incorrect", date_str, child_id, tier_key, word,
            ),
        )

    conn.commit()
    _maybe_advance_tier(conn, child_id)
    return session_id


def _maybe_advance_tier(conn: sqlite3.Connection, child_id: int) -> None:
    child = get_child(conn, child_id)
    tier_key = child["current_tier"]
    idx = tier_index(tier_key)
    if idx >= len(TIERS) - 1:
        return
    states = get_word_states(conn, child_id, tier_key)
    if states and all(s.status == STATUS_KNOWN for s in states):
        next_tier = TIERS[idx + 1]
        conn.execute("UPDATE children SET current_tier = ? WHERE id = ?", (next_tier.key, child_id))
        _seed_tier(conn, child_id, next_tier.key, known_words=set())
        conn.commit()


def get_sessions(conn: sqlite3.Connection, child_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sessions WHERE child_id = ? ORDER BY date DESC, id DESC", (child_id,)
    ).fetchall()


def get_session_words(conn: sqlite3.Connection, session_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT word, correct FROM session_words WHERE session_id = ?", (session_id,)
    ).fetchall()


# ----------------------------------------------------------------------
# Game scores (used by the on-screen games - see games_ui.py)
# ----------------------------------------------------------------------
def record_game_score(conn: sqlite3.Connection, child_id: int, game: str, date_str: str, score: float, metric: str) -> None:
    conn.execute(
        "INSERT INTO game_scores (child_id, game, date, score, metric, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (child_id, game, date_str, score, metric, _now_iso()),
    )
    conn.commit()


def get_game_scores(conn: sqlite3.Connection, child_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM game_scores WHERE child_id = ? ORDER BY date DESC, id DESC", (child_id,)
    ).fetchall()
