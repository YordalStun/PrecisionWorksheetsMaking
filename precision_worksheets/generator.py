"""Core logic for building Precision Teaching probe sheets.

A probe sheet is a grid of cells filled with a small set of target words,
repeated and shuffled so a child can practise reading them fluently
("see it, say it") against the clock. This module only builds the data
(which word goes in which cell) - pdf_export.py and docx_export.py turn
that data into printable files.

This is deliberately kept separate from the PDF/Word/GUI code so the same
word-grid logic can be reused later for other practice tools (e.g. a
board-game layout) without duplicating the shuffling rules.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class ProbeSheet:
    """One printable probe sheet: a header plus a rows x cols word grid."""

    child_name: str
    date_str: str
    words: list[str]
    grid: list[list[str]]
    sheet_number: int
    total_sheets: int

    @property
    def rows(self) -> int:
        return len(self.grid)

    @property
    def cols(self) -> int:
        return len(self.grid[0]) if self.grid else 0


def generate_word_grid(
    words: list[str],
    rows: int,
    cols: int,
    rng: random.Random | None = None,
) -> list[list[str]]:
    """Build a rows x cols grid drawing evenly from `words`.

    Each word appears (almost) exactly as often as every other word, and no
    two cells that are next to each other in reading order (left-to-right,
    then wrapping to the next row) hold the same word - so a child can't
    just read the same word repeatedly without looking.
    """
    if not words:
        raise ValueError("At least one word is required")
    if rows < 1 or cols < 1:
        raise ValueError("rows and cols must be at least 1")

    rng = rng or random.Random()
    total_cells = rows * cols

    sequence: list[str] = []
    while len(sequence) < total_cells:
        cycle = list(words)
        rng.shuffle(cycle)
        # Avoid a repeat forming right where this cycle joins the last one.
        if sequence and cycle[0] == sequence[-1] and len(cycle) > 1:
            for i in range(1, len(cycle)):
                if cycle[i] != sequence[-1]:
                    cycle[0], cycle[i] = cycle[i], cycle[0]
                    break
        sequence.extend(cycle)
    sequence = sequence[:total_cells]

    if len(set(words)) > 1:
        sequence = _remove_adjacent_repeats(sequence, rng)

    return [sequence[r * cols:(r + 1) * cols] for r in range(rows)]


def _remove_adjacent_repeats(
    sequence: list[str], rng: random.Random, max_passes: int = 10
) -> list[str]:
    """Swap cells so no two consecutive entries in the sequence match.

    Best-effort: with an even word frequency this always succeeds in
    practice, but it will quietly give up rather than loop forever on a
    pathological input.
    """
    seq = sequence[:]
    n = len(seq)
    for _ in range(max_passes):
        conflict = next((i for i in range(1, n) if seq[i] == seq[i - 1]), None)
        if conflict is None:
            return seq
        for j in range(conflict + 1, n):
            if seq[j] == seq[conflict]:
                continue
            if seq[j] == seq[conflict - 1]:
                continue
            if j + 1 < n and seq[j + 1] == seq[conflict]:
                continue
            seq[conflict], seq[j] = seq[j], seq[conflict]
            break
        else:
            # No safe swap found anywhere later in the sequence - try once
            # more from the top of the shuffle on the next pass, or give up.
            rng.shuffle(seq)
    return seq


def build_probe_sheets(
    child_name: str,
    words: list[str],
    num_sheets: int,
    rows: int,
    cols: int,
    date_str: str,
    seed: int | None = None,
) -> list[ProbeSheet]:
    """Build `num_sheets` independently-shuffled ProbeSheet objects."""
    rng = random.Random(seed)
    clean_words = [w.strip() for w in words if w.strip()]
    if not clean_words:
        raise ValueError("At least one word is required")
    if num_sheets < 1:
        raise ValueError("num_sheets must be at least 1")

    sheets = []
    for n in range(1, num_sheets + 1):
        grid = generate_word_grid(clean_words, rows, cols, rng)
        sheets.append(
            ProbeSheet(
                child_name=child_name,
                date_str=date_str,
                words=clean_words,
                grid=grid,
                sheet_number=n,
                total_sheets=num_sheets,
            )
        )
    return sheets
