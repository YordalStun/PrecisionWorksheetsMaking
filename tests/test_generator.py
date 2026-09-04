import random
import unittest
from collections import Counter

from precision_worksheets.generator import build_probe_sheets, generate_word_grid


class TestGenerateWordGrid(unittest.TestCase):
    def test_dimensions(self):
        grid = generate_word_grid(["a", "b", "c", "d", "e"], rows=6, cols=5, rng=random.Random(1))
        self.assertEqual(len(grid), 6)
        self.assertTrue(all(len(row) == 5 for row in grid))

    def test_even_word_frequency(self):
        words = ["cat", "dog", "sun", "run", "big"]
        grid = generate_word_grid(words, rows=10, cols=10, rng=random.Random(7))
        flat = [w for row in grid for w in row]
        counts = Counter(flat)
        self.assertEqual(set(counts), set(words))
        # 100 cells / 5 words = exactly 20 each.
        self.assertTrue(all(c == 20 for c in counts.values()))

    def test_no_adjacent_repeats_in_reading_order(self):
        words = ["cat", "dog", "sun"]
        for seed in range(20):
            grid = generate_word_grid(words, rows=8, cols=6, rng=random.Random(seed))
            flat = [w for row in grid for w in row]
            for i in range(1, len(flat)):
                self.assertNotEqual(flat[i], flat[i - 1], f"seed={seed} pos={i}")

    def test_single_word_does_not_crash(self):
        grid = generate_word_grid(["only"], rows=3, cols=3, rng=random.Random(1))
        self.assertEqual(sum(row.count("only") for row in grid), 9)

    def test_rejects_empty_word_list(self):
        with self.assertRaises(ValueError):
            generate_word_grid([], rows=3, cols=3)

    def test_rejects_bad_dimensions(self):
        with self.assertRaises(ValueError):
            generate_word_grid(["a"], rows=0, cols=3)


class TestBuildProbeSheets(unittest.TestCase):
    def test_builds_requested_number_of_sheets(self):
        sheets = build_probe_sheets(
            "Alex", ["cat", "dog", "sun", "run", "big"], num_sheets=4,
            rows=5, cols=5, date_str="04/09/2026", seed=1,
        )
        self.assertEqual(len(sheets), 4)
        for i, sheet in enumerate(sheets, start=1):
            self.assertEqual(sheet.sheet_number, i)
            self.assertEqual(sheet.total_sheets, 4)
            self.assertEqual(sheet.child_name, "Alex")
            self.assertEqual(sheet.rows, 5)
            self.assertEqual(sheet.cols, 5)

    def test_sheets_are_independently_shuffled(self):
        sheets = build_probe_sheets(
            "Sam", ["a", "b", "c", "d", "e"], num_sheets=5,
            rows=6, cols=6, date_str="04/09/2026", seed=99,
        )
        flat_versions = {tuple(w for row in s.grid for w in row) for s in sheets}
        # Vanishingly unlikely for a 36-cell shuffle to repeat by chance.
        self.assertEqual(len(flat_versions), 5)

    def test_strips_and_ignores_blank_words(self):
        sheets = build_probe_sheets(
            "Sam", [" cat ", "dog", "", "  ", "sun"], num_sheets=1,
            rows=3, cols=3, date_str="04/09/2026", seed=1,
        )
        self.assertEqual(sheets[0].words, ["cat", "dog", "sun"])

    def test_rejects_zero_sheets(self):
        with self.assertRaises(ValueError):
            build_probe_sheets("Sam", ["a"], num_sheets=0, rows=3, cols=3, date_str="x")


if __name__ == "__main__":
    unittest.main()
