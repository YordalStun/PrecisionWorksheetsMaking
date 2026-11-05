"""Word mastery rules and the weekly word-picking logic.

Mastery rule: a word needs 3 CONSECUTIVE correct reads to count as known.
A miss at any point - even on a word that was already known - resets its
streak to zero and drops it straight back into the practice pool, so a
word that's only been got right once or twice before a slip keeps coming
back until it's solid.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

MASTERY_STREAK = 3

STATUS_LEARNING = "learning"
STATUS_KNOWN = "known"


@dataclass
class WordState:
    word: str
    status: str
    correct_streak: int
    times_seen: int
    times_correct: int


def apply_result(state: WordState, correct: bool) -> WordState:
    """Return the updated state for a word after one more read."""
    times_seen = state.times_seen + 1
    times_correct = state.times_correct + (1 if correct else 0)
    if correct:
        streak = state.correct_streak + 1
        status = STATUS_KNOWN if streak >= MASTERY_STREAK else STATUS_LEARNING
    else:
        streak = 0
        status = STATUS_LEARNING
    return WordState(state.word, status, streak, times_seen, times_correct)


def pick_practice_words(learning_words_in_tier_order: list[WordState], num_words: int = 3) -> list[str]:
    """Pick the words to practise this week, most in-need first.

    Words already being worked on (tried at least once, not yet mastered -
    this is where a struggling word keeps reappearing) come before words
    that haven't been introduced yet. Fresh words are introduced in the
    tier's own canonical order, so "the next word" always means the next
    one in the published list, not a random pick.
    """
    in_progress = [w for w in learning_words_in_tier_order if w.times_seen > 0]
    fresh = [w for w in learning_words_in_tier_order if w.times_seen == 0]
    ordered = in_progress + fresh
    return [w.word for w in ordered[:num_words]]


def pick_known_words(known_words: list[str], rng: random.Random, num_words: int = 2) -> list[str]:
    """Pick `num_words` already-known words at random, to mix in with the
    practice words - if there aren't enough known words yet, just use
    whatever's available."""
    if len(known_words) <= num_words:
        return list(known_words)
    return rng.sample(known_words, num_words)
