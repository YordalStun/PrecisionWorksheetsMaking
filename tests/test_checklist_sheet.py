import os
import tempfile
import unittest

from precision_worksheets.checklist_sheet import (
    WORDS_PER_PAGE,
    checkbox_centres,
    export_checklist_pdf,
    marker_positions,
    paginate,
)
from precision_worksheets.data.word_lists import FIRST_100, NEXT_200, YEAR_3_4


class TestPaginate(unittest.TestCase):
    def test_covers_every_word_in_order_across_pages(self):
        pages = paginate("first100")
        words = [w for page in pages for w in page.words]
        self.assertEqual(words, list(FIRST_100))

    def test_pages_are_at_most_one_page_worth_of_words(self):
        for page in paginate("next200"):
            self.assertLessEqual(len(page.words), WORDS_PER_PAGE)

    def test_total_pages_consistent_on_every_page(self):
        pages = paginate("year34")
        for page in pages:
            self.assertEqual(page.total_pages, len(pages))

    def test_page_count_matches_word_count(self):
        import math

        self.assertEqual(len(paginate("first100")), math.ceil(len(FIRST_100) / WORDS_PER_PAGE))
        self.assertEqual(len(paginate("next200")), math.ceil(len(NEXT_200) / WORDS_PER_PAGE))
        self.assertEqual(len(paginate("year34")), math.ceil(len(YEAR_3_4) / WORDS_PER_PAGE))


class TestCheckboxLayout(unittest.TestCase):
    def test_one_centre_per_word(self):
        self.assertEqual(len(checkbox_centres(37)), 37)

    def test_four_distinct_markers(self):
        positions = marker_positions()
        self.assertEqual(set(positions.keys()), {"tl", "tr", "bl", "br"})
        self.assertEqual(len(set(positions.values())), 4)


class TestExportPdf(unittest.TestCase):
    def test_writes_one_page_per_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "checklist.pdf")
            export_checklist_pdf("first100", path, child_name="Alex")
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 0)

    def test_known_words_round_trips_through_a_scan(self):
        """A checklist pre-filled with known_words (e.g. carrying over an
        earlier paper assessment) should read back exactly via the real
        OMR pipeline, same as a hand-ticked one."""
        from PIL import Image

        from precision_worksheets import omr
        from precision_worksheets.checklist_sheet import paginate
        from precision_worksheets.data.word_lists import FIRST_100

        known = set(FIRST_100[:5]) | set(FIRST_100[50:53])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "checklist.pdf")
            export_checklist_pdf("first100", path, known_words=known)

            import fitz  # PyMuPDF

            doc = fitz.open(path)
            try:
                detected: set[str] = set()
                pages = paginate("first100")
                for page, pdf_page in zip(pages, doc):
                    pix = pdf_page.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), colorspace=fitz.csGRAY)
                    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                    result = omr.read_page(img, page)
                    detected.update(w for w, ticked in result.words.items() if ticked)
            finally:
                doc.close()

        self.assertEqual(detected, known)


if __name__ == "__main__":
    unittest.main()
