import math
import os
import tempfile
import unittest

from precision_worksheets.games._fun import PAGE_H, PAGE_W
from precision_worksheets.games.adventure_boards import (
    BOARD_BOX,
    BONUS,
    FINISH,
    HAZARD,
    LEGEND_BOTTOM,
    START,
    THEME_CHOICES,
    THEMES,
    WORD,
    _spaces_fit,
    build_adventure_board,
    build_adventure_boards,
    export_adventure_docx,
    export_adventure_pdf,
    render_adventure_image,
)

WORDS = ["cat", "dog", "sun", "run", "big"]


class TestBuildAdventureBoard(unittest.TestCase):
    def test_rejects_empty_words_and_unknown_theme(self):
        with self.assertRaises(ValueError):
            build_adventure_board("Alex", ["  ", ""])
        with self.assertRaises(ValueError):
            build_adventure_board("Alex", WORDS, theme="volcano")

    def test_start_and_finish_at_the_ends(self):
        for theme in THEME_CHOICES:
            board = build_adventure_board("Alex", WORDS, theme=theme, seed=1)
            self.assertEqual(board.spaces[0].kind, START)
            self.assertEqual(board.spaces[-1].kind, FINISH)
            self.assertEqual([s.kind for s in board.spaces].count(START), 1)
            self.assertEqual([s.kind for s in board.spaces].count(FINISH), 1)

    def test_spaces_never_overlap_and_stay_on_the_board(self):
        for theme in THEME_CHOICES:
            for seed in range(60):
                board = build_adventure_board("Alex", WORDS, theme=theme, seed=seed)
                self.assertTrue(_spaces_fit(board.positions, board.radii), f"{theme} seed={seed}")

    def test_every_word_used_and_no_word_twice_in_a_row(self):
        for theme in THEME_CHOICES:
            for seed in range(20):
                board = build_adventure_board("Alex", WORDS, theme=theme, seed=seed)
                words = [s.word for s in board.spaces if s.kind == WORD]
                self.assertEqual(set(words), set(WORDS))
                for a, b in zip(board.spaces, board.spaces[1:]):
                    if a.kind == b.kind == WORD:
                        self.assertNotEqual(a.word, b.word)

    def test_special_spaces_always_send_you_to_a_word_space(self):
        for theme in THEME_CHOICES:
            info = THEMES[theme]
            for seed in range(40):
                board = build_adventure_board("Alex", WORDS, theme=theme, seed=seed)
                kinds = [s.kind for s in board.spaces]
                self.assertGreaterEqual(kinds.count(BONUS), 1)
                self.assertGreaterEqual(kinds.count(HAZARD), 1)
                for i, k in enumerate(kinds):
                    if k == BONUS and info.bonus_move:
                        self.assertEqual(kinds[i + info.bonus_move], WORD)
                    if k == HAZARD:
                        self.assertEqual(kinds[i - info.hazard_move], WORD)

    def test_same_seed_same_board_different_seed_different_board(self):
        a = build_adventure_board("Alex", WORDS, theme="treasure", seed=5)
        b = build_adventure_board("Alex", WORDS, theme="treasure", seed=5)
        c = build_adventure_board("Alex", WORDS, theme="treasure", seed=6)
        self.assertEqual(a.positions, b.positions)
        self.assertEqual([s.word for s in a.spaces], [s.word for s in b.spaces])
        self.assertNotEqual(a.positions, c.positions)

    def test_random_theme_and_mix(self):
        board = build_adventure_board("Alex", WORDS, theme="random", seed=3)
        self.assertIn(board.theme, THEME_CHOICES)
        boards = build_adventure_boards("Alex", WORDS, theme="mix", count=4, seed=2)
        self.assertEqual(sorted(b.theme for b in boards), sorted(THEME_CHOICES))

    def test_works_with_one_word_and_many_long_words(self):
        build_adventure_board("Alex", ["cat"], seed=1)
        long_words = ["caterpillar", "Wednesday", "beautiful", "because", "through", "thought", "people", "friends"]
        board = build_adventure_board("Alex", long_words, theme="rainbow", seed=1)
        self.assertEqual({s.word for s in board.spaces if s.kind == WORD}, set(long_words))


class TestRenderAndExport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_every_theme_renders_a4_and_footer_stays_on_the_page(self):
        self.assertLess(BOARD_BOX[3], LEGEND_BOTTOM)
        self.assertLessEqual(LEGEND_BOTTOM, PAGE_H - 20)
        for theme in THEME_CHOICES:
            img = render_adventure_image(build_adventure_board("", WORDS, theme=theme, seed=4))
            self.assertEqual(img.size, (PAGE_W, PAGE_H))

    def test_multi_board_pdf_and_docx(self):
        boards = build_adventure_boards("Alex", WORDS, count=2, seed=1)
        pdf = os.path.join(self.tmpdir.name, "b.pdf")
        export_adventure_pdf(boards, pdf)
        with open(pdf, "rb") as f:
            data = f.read()
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertEqual(data.count(b"/Type /Page\n") + data.count(b"/Type /Page "), 2)

        from docx import Document

        docx_path = os.path.join(self.tmpdir.name, "b.docx")
        export_adventure_docx(boards, docx_path)
        doc = Document(docx_path)
        self.assertEqual(len(doc.inline_shapes), 2)


if __name__ == "__main__":
    unittest.main()
