import os
import tempfile
import unittest

from precision_worksheets.games.snakes_and_ladders import (
    BOARD_SIZE,
    build_board,
    export_board_docx,
    export_board_pdf,
    render_board_image,
    _square_center,
    _square_number_at,
)


class TestSquareNumbering(unittest.TestCase):
    def test_center_and_number_at_are_inverses_for_every_square(self):
        from precision_worksheets.games.snakes_and_ladders import BOARD_LEFT, BOARD_TOP, CELL_SIZE

        for n in range(1, 101):
            x, y = _square_center(n)
            col = int((x - BOARD_LEFT) // CELL_SIZE)
            row = int((y - BOARD_TOP) // CELL_SIZE)
            self.assertEqual(_square_number_at(row, col), n)

    def test_square_one_is_bottom_left_square_100_is_top_left(self):
        from precision_worksheets.games.snakes_and_ladders import BOARD_LEFT, BOARD_TOP, CELL_SIZE

        x1, y1 = _square_center(1)
        self.assertAlmostEqual(x1, BOARD_LEFT + CELL_SIZE / 2)
        self.assertAlmostEqual(y1, BOARD_TOP + (BOARD_SIZE - 0.5) * CELL_SIZE)

        x100, y100 = _square_center(100)
        self.assertAlmostEqual(x100, BOARD_LEFT + CELL_SIZE / 2)
        self.assertAlmostEqual(y100, BOARD_TOP + CELL_SIZE / 2)


class TestBuildBoard(unittest.TestCase):
    def test_rejects_empty_word_list(self):
        with self.assertRaises(ValueError):
            build_board("Alex", [])

    def test_no_square_is_both_a_ladder_and_a_snake_endpoint(self):
        board = build_board("Alex", ["cat", "dog", "sun", "run", "big"], seed=3)
        ladder_squares = set(board.ladders) | set(board.ladders.values())
        snake_squares = set(board.snakes) | set(board.snakes.values())
        self.assertEqual(ladder_squares & snake_squares, set())

    def test_ladders_go_up_and_snakes_go_down(self):
        board = build_board("Alex", ["cat", "dog", "sun", "run", "big"], seed=3)
        for start, end in board.ladders.items():
            self.assertGreater(end, start)
        for start, end in board.snakes.items():
            self.assertLess(end, start)

    def test_word_squares_do_not_collide_with_ladders_or_snakes(self):
        board = build_board("Alex", ["cat", "dog", "sun", "run", "big"], seed=3)
        feature_squares = set(board.ladders) | set(board.ladders.values()) | set(board.snakes) | set(board.snakes.values())
        self.assertEqual(set(board.word_squares) & feature_squares, set())

    def test_start_and_end_squares_are_never_features(self):
        board = build_board("Alex", ["cat", "dog", "sun", "run", "big"], seed=3)
        all_features = set(board.ladders) | set(board.ladders.values()) | set(board.snakes) | set(board.snakes.values()) | set(board.word_squares)
        self.assertNotIn(1, all_features)
        self.assertNotIn(100, all_features)

    def test_every_target_word_appears_on_the_board(self):
        words = ["cat", "dog", "sun", "run", "big"]
        board = build_board("Alex", words, seed=3)
        self.assertEqual(set(board.word_squares.values()), set(words))


class TestSnakesAndLaddersExport(unittest.TestCase):
    def setUp(self):
        self.board = build_board("Alex", ["cat", "dog", "sun", "run", "big"], seed=1)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_render_board_image_is_a4_shaped(self):
        from precision_worksheets.games.snakes_and_ladders import IMG_WIDTH, IMG_HEIGHT

        img = render_board_image(self.board)
        self.assertEqual(img.size, (IMG_WIDTH, IMG_HEIGHT))

    def test_export_pdf_is_a_single_a4_page(self):
        path = os.path.join(self.tmpdir.name, "board.pdf")
        export_board_pdf(self.board, path)
        with open(path, "rb") as f:
            data = f.read()
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertEqual(data.count(b"/Type /Page"), 2)

    def test_export_docx_is_a4(self):
        from docx import Document
        from docx.shared import Cm

        path = os.path.join(self.tmpdir.name, "board.docx")
        export_board_docx(self.board, path)
        doc = Document(path)
        section = doc.sections[0]
        self.assertAlmostEqual(section.page_width / Cm(1), 21.0, places=1)
        self.assertAlmostEqual(section.page_height / Cm(1), 29.7, places=1)

    def test_render_is_repeatable_for_the_same_board(self):
        a = render_board_image(self.board)
        b = render_board_image(self.board)
        self.assertEqual(a.tobytes(), b.tobytes())


class TestBoardMakesSense(unittest.TestCase):
    """The placement rules that keep every random board readable."""

    WORDS = ["cat", "dog", "sun", "run", "big"]

    def _features(self, board):
        from precision_worksheets.games.snakes_and_ladders import _grid_point

        return [(_grid_point(a), _grid_point(b)) for a, b in list(board.ladders.items()) + list(board.snakes.items())]

    def test_no_ladders_or_snakes_cross_each_other(self):
        from precision_worksheets.games.snakes_and_ladders import _segments_gap

        for seed in range(40):
            feats = self._features(build_board("Alex", self.WORDS, seed=seed))
            for i in range(len(feats)):
                for j in range(i + 1, len(feats)):
                    self.assertGreater(_segments_gap(*feats[i], *feats[j]), 0.5, f"seed={seed}")

    def test_no_ladder_or_snake_passes_over_a_word_square(self):
        from precision_worksheets.games.snakes_and_ladders import _grid_point, _seg_dist

        for seed in range(40):
            board = build_board("Alex", self.WORDS, seed=seed)
            for n in board.word_squares:
                for a, b in self._features(board):
                    self.assertGreaterEqual(_seg_dist(_grid_point(n), a, b), 0.6, f"seed={seed} square={n}")

    def test_ladders_and_snakes_are_short_and_mostly_upright(self):
        from precision_worksheets.games.snakes_and_ladders import MAX_ROWS_SPANNED, _row_col

        for seed in range(40):
            board = build_board("Alex", self.WORDS, seed=seed)
            for a, b in list(board.ladders.items()) + list(board.snakes.items()):
                (ra, ca), (rb, cb) = _row_col(a), _row_col(b)
                rows = abs(ra - rb)
                self.assertTrue(1 <= rows <= MAX_ROWS_SPANNED)
                self.assertLessEqual(abs(ca - cb), rows + 1)

    def test_full_set_of_features_and_words_is_placed(self):
        from precision_worksheets.games.snakes_and_ladders import N_LADDERS, N_SNAKES, WORD_SQUARE_REPEATS

        for seed in range(40):
            board = build_board("Alex", self.WORDS, seed=seed)
            self.assertEqual(len(board.ladders), N_LADDERS)
            self.assertEqual(len(board.snakes), N_SNAKES)
            self.assertEqual(len(board.word_squares), len(self.WORDS) * WORD_SQUARE_REPEATS)

    def test_boards_differ_without_a_seed(self):
        boards = [build_board("Alex", self.WORDS) for _ in range(3)]
        layouts = {(tuple(sorted(b.ladders.items())), tuple(sorted(b.snakes.items()))) for b in boards}
        self.assertGreater(len(layouts), 1)

if __name__ == "__main__":
    unittest.main()
