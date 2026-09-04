import unittest

from reportlab.pdfbase import pdfmetrics

from precision_worksheets.layout import MIN_GRID_FONT_SIZE, fit_grid_font_size


class TestFitGridFontSize(unittest.TestCase):
    def test_keeps_cap_when_word_already_fills_it(self):
        # A wide box and a short word - the cap itself already fits.
        size = fit_grid_font_size(["cat", "dog"], max_size=18, cell_width_pt=300)
        self.assertEqual(size, 18)

    def test_grows_short_words_up_towards_the_cap_in_a_roomy_box(self):
        # This is the point of the "as big as possible" behaviour: a short
        # word in a generous box should end up much bigger than some small
        # fixed default, right up to (or near) the cap.
        size = fit_grid_font_size(["cat"], max_size=60, cell_width_pt=300)
        self.assertGreater(size, 40)

    def test_shrinks_when_word_is_too_wide_for_the_box(self):
        narrow_cell_pt = 40
        size = fit_grid_font_size(["extraordinarily"], max_size=18, cell_width_pt=narrow_cell_pt)
        self.assertLess(size, 18)

    def test_shrunk_text_fits_the_box_when_a_fitting_size_exists(self):
        from precision_worksheets.fonts import get_comic_font_names

        _, bold_font = get_comic_font_names()
        words = ["extraordinarily", "magnificent"]
        cell_width_pt = 150  # roomy enough that some size above the floor fits
        size = fit_grid_font_size(words, max_size=24, cell_width_pt=cell_width_pt)
        widest = max(pdfmetrics.stringWidth(w, bold_font, size) for w in words)
        self.assertLessEqual(widest, cell_width_pt * 0.85 + 0.01)
        self.assertGreater(size, MIN_GRID_FONT_SIZE)

    def test_never_shrinks_below_the_minimum(self):
        size = fit_grid_font_size(
            ["supercalifragilisticexpialidocious"], max_size=18, cell_width_pt=20
        )
        self.assertEqual(size, MIN_GRID_FONT_SIZE)

    def test_empty_word_list_returns_the_cap(self):
        size = fit_grid_font_size([], max_size=18, cell_width_pt=50)
        self.assertEqual(size, 18)


if __name__ == "__main__":
    unittest.main()
