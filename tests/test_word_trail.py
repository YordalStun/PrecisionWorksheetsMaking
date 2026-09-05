import os
import tempfile
import unittest
from collections import Counter

from precision_worksheets.games.word_trail import (
    CIRCLES_PER_ROW,
    NUM_ROWS,
    _build_path_positions,
    _layout_for,
    build_word_trail,
    export_word_trail_docx,
    export_word_trail_pdf,
    render_trail_image,
)


class TestBuildWordTrail(unittest.TestCase):
    def test_total_circles_matches_rows_and_connectors(self):
        trail = build_word_trail("Alex", ["cat", "dog", "sun", "run", "big"], seed=1)
        expected = NUM_ROWS * CIRCLES_PER_ROW + (NUM_ROWS - 1)
        self.assertEqual(len(trail.trail), expected)

    def test_every_word_appears_and_no_adjacent_repeats(self):
        words = ["cat", "dog", "sun", "run", "big"]
        for seed in range(10):
            trail = build_word_trail("Alex", words, seed=seed)
            self.assertEqual(set(trail.trail), set(words))
            for i in range(1, len(trail.trail)):
                self.assertNotEqual(trail.trail[i], trail.trail[i - 1], f"seed={seed} pos={i}")

    def test_rejects_empty_word_list(self):
        with self.assertRaises(ValueError):
            build_word_trail("Alex", [])


class TestPathLayout(unittest.TestCase):
    def test_positions_count_matches_trail_length(self):
        trail = build_word_trail("Alex", ["cat", "dog", "sun", "run", "big"], seed=1)
        layout = _layout_for("A4")
        self.assertEqual(len(_build_path_positions(layout)), len(trail.trail))

    def test_no_circle_is_clipped_off_the_page(self):
        for page_size in ("A4", "A3"):
            layout = _layout_for(page_size)
            radius = layout.circle_diameter / 2
            for x, y in _build_path_positions(layout):
                self.assertGreaterEqual(x - radius, 0, f"{page_size} clipped left at x={x}")
                self.assertLessEqual(x + radius, layout.img_width, f"{page_size} clipped right at x={x}")
                self.assertGreaterEqual(y - radius, 0, f"{page_size} clipped top at y={y}")

    def test_a3_is_scaled_up_from_a4_by_the_same_factor_everywhere(self):
        a4 = _layout_for("A4")
        a3 = _layout_for("A3")
        ratio = a3.img_width / a4.img_width
        self.assertAlmostEqual(a3.circle_diameter / a4.circle_diameter, ratio)
        self.assertAlmostEqual(a3.margin / a4.margin, ratio)
        self.assertAlmostEqual(a3.row_spacing / a4.row_spacing, ratio)

    def test_rejects_unknown_page_size(self):
        with self.assertRaises(ValueError):
            _layout_for("Letter")


class TestWordTrailExport(unittest.TestCase):
    def setUp(self):
        self.trail = build_word_trail("Alex", ["cat", "dog", "sun", "run", "big"], seed=1)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_render_trail_image_a4_and_a3_sizes(self):
        img_a4 = render_trail_image(self.trail, page_size="A4")
        img_a3 = render_trail_image(self.trail, page_size="A3")
        self.assertEqual(img_a4.size, (1654, 2339))
        # A3 has double the area of A4 at the same aspect ratio.
        self.assertGreater(img_a3.size[0], img_a4.size[0])
        self.assertAlmostEqual(img_a3.size[0] / img_a4.size[0], img_a3.size[1] / img_a4.size[1], places=2)

    def test_export_pdf_is_a_single_page_for_each_size(self):
        for page_size in ("A4", "A3"):
            path = os.path.join(self.tmpdir.name, f"trail_{page_size}.pdf")
            export_word_trail_pdf(self.trail, path, page_size=page_size)
            with open(path, "rb") as f:
                data = f.read()
            self.assertTrue(data.startswith(b"%PDF-"))
            self.assertEqual(data.count(b"/Type /Page"), 2)

    def test_export_docx_page_size_matches(self):
        from docx import Document
        from docx.shared import Cm

        for page_size, expected_cm in (("A4", (21.0, 29.7)), ("A3", (29.7, 42.0))):
            path = os.path.join(self.tmpdir.name, f"trail_{page_size}.docx")
            export_word_trail_docx(self.trail, path, page_size=page_size)
            doc = Document(path)
            section = doc.sections[0]
            self.assertAlmostEqual(section.page_width / Cm(1), expected_cm[0], places=1)
            self.assertAlmostEqual(section.page_height / Cm(1), expected_cm[1], places=1)


if __name__ == "__main__":
    unittest.main()
