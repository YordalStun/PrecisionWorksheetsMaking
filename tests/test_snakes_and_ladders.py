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

    def test_word_squares_are_redrawn_on_top_of_ladders_and_snakes(self):
        """A ladder/snake between two other squares can pass straight
        through a word square along the way - it must not end up drawn
        over that word square's fill/text, or the word becomes unreadable."""
        from unittest import mock

        from PIL import ImageDraw

        from precision_worksheets.games import snakes_and_ladders as sal

        board = build_board("Alex", ["cat", "dog", "sun", "run", "big"], seed=1)
        self.assertTrue(board.ladders)
        self.assertTrue(board.snakes)

        events: list[tuple[str, int]] = []
        orig_rectangle = ImageDraw.ImageDraw.rectangle
        orig_draw_ladder = sal._draw_ladder
        orig_draw_snake = sal._draw_snake

        def tracking_rectangle(self, xy, fill=None, **kwargs):
            # Only count full board-cell fills, not the small legend swatch
            # (drawn later, also in COLOR_WORD_SQUARE, but not a cell).
            is_cell_sized = abs((xy[2] - xy[0]) - sal.CELL_SIZE * sal.SUPERSAMPLE) < 1
            if fill == sal.COLOR_WORD_SQUARE and is_cell_sized:
                events.append(("word_square", len(events)))
            return orig_rectangle(self, xy, fill=fill, **kwargs)

        def tracking_ladder(*args, **kwargs):
            events.append(("ladder", len(events)))
            return orig_draw_ladder(*args, **kwargs)

        def tracking_snake(*args, **kwargs):
            events.append(("snake", len(events)))
            return orig_draw_snake(*args, **kwargs)

        with mock.patch.object(ImageDraw.ImageDraw, "rectangle", tracking_rectangle), \
             mock.patch.object(sal, "_draw_ladder", tracking_ladder), \
             mock.patch.object(sal, "_draw_snake", tracking_snake):
            sal.render_board_image(board)

        last_feature_index = max(i for kind, i in events if kind in ("ladder", "snake"))
        word_square_indices = [i for kind, i in events if kind == "word_square"]
        # Every word square is filled twice: once in the initial grid pass,
        # then again afterwards - that final redraw must land after every
        # ladder and snake so it's the last thing painted there.
        self.assertEqual(len(word_square_indices), 2 * len(board.word_squares))
        final_redraws = word_square_indices[-len(board.word_squares):]
        self.assertTrue(all(i > last_feature_index for i in final_redraws))


if __name__ == "__main__":
    unittest.main()
