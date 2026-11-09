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


if __name__ == "__main__":
    unittest.main()
