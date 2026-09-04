import os
import tempfile
import unittest

from docx import Document

from precision_worksheets.games.word_search import (
    DIRECTIONS,
    MIN_GRID_SIZE,
    build_word_search,
    export_word_search_docx,
    export_word_search_pdf,
)


def _find_word(grid: list[list[str]], word: str, size: int) -> bool:
    for dr, dc in DIRECTIONS:
        for row in range(size):
            for col in range(size):
                ok = True
                for i, letter in enumerate(word):
                    r, c = row + i * dr, col + i * dc
                    if not (0 <= r < size and 0 <= c < size) or grid[r][c] != letter:
                        ok = False
                        break
                if ok:
                    return True
    return False


class TestBuildWordSearch(unittest.TestCase):
    def test_every_word_is_actually_findable(self):
        words = ["cat", "dog", "sun", "run", "big"]
        for seed in range(15):
            puzzle = build_word_search("Alex", words, seed=seed)
            for word in words:
                self.assertTrue(
                    _find_word(puzzle.grid, word.upper(), puzzle.size),
                    f"{word!r} not found in grid (seed={seed})",
                )

    def test_grid_is_square_and_at_least_the_minimum_size(self):
        puzzle = build_word_search("Alex", ["cat", "dog", "sun", "run", "big"], seed=1)
        self.assertGreaterEqual(puzzle.size, MIN_GRID_SIZE)
        self.assertTrue(all(len(row) == puzzle.size for row in puzzle.grid))

    def test_grid_grows_to_fit_long_words(self):
        words = ["elephant", "beautiful", "wonderful", "fantastic", "crocodile"]
        puzzle = build_word_search("Alex", words, seed=1)
        self.assertGreaterEqual(puzzle.size, max(len(w) for w in words))
        for word in words:
            self.assertTrue(_find_word(puzzle.grid, word.upper(), puzzle.size))

    def test_every_cell_is_an_uppercase_letter(self):
        puzzle = build_word_search("Alex", ["cat", "dog", "sun", "run", "big"], seed=1)
        for row in puzzle.grid:
            for cell in row:
                self.assertEqual(len(cell), 1)
                self.assertTrue(cell.isalpha())
                self.assertTrue(cell.isupper())

    def test_rejects_empty_word_list(self):
        with self.assertRaises(ValueError):
            build_word_search("Alex", [])


class TestWordSearchExport(unittest.TestCase):
    def setUp(self):
        self.puzzle = build_word_search("Alex", ["cat", "dog", "sun", "run", "big"], seed=1)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_export_pdf_is_a_single_page(self):
        path = os.path.join(self.tmpdir.name, "ws.pdf")
        export_word_search_pdf(self.puzzle, path)
        with open(path, "rb") as f:
            data = f.read()
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertEqual(data.count(b"/Type /Page"), 2)

    def test_export_docx_grid_matches_puzzle(self):
        path = os.path.join(self.tmpdir.name, "ws.docx")
        export_word_search_docx(self.puzzle, path)
        doc = Document(path)
        table = doc.tables[0]
        self.assertEqual(len(table.rows), self.puzzle.size)
        self.assertEqual(len(table.columns), self.puzzle.size)
        for r in range(self.puzzle.size):
            for c in range(self.puzzle.size):
                self.assertEqual(table.rows[r].cells[c].text, self.puzzle.grid[r][c])


if __name__ == "__main__":
    unittest.main()
