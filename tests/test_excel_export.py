import os
import tempfile
import unittest

from openpyxl import load_workbook

from precision_worksheets import db
from precision_worksheets.data.word_lists import FIRST_100
from precision_worksheets.excel_export import export_child_report


class TestExcelExport(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def _path(self, name="report.xlsx"):
        return os.path.join(self.tmpdir.name, name)

    def test_raises_for_missing_child(self):
        with self.assertRaises(ValueError):
            export_child_report(self.conn, 999, self._path())

    def test_overview_and_word_list_sheets(self):
        known = set(FIRST_100[:20])
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", known)
        path = self._path()
        export_child_report(self.conn, child_id, path)
        self.assertTrue(os.path.exists(path))

        wb = load_workbook(path)
        self.assertEqual(
            wb.sheetnames, ["Overview", "Current Word List", "Session History", "Session Word Detail"]
        )

        overview = wb["Overview"]
        self.assertEqual(overview["A1"].value, "Alex")
        self.assertIn("Year 1", overview["A2"].value)

        words = wb["Current Word List"]
        self.assertEqual([c.value for c in words[1]], [
            "Word", "Status", "Correct streak", "Times seen", "Times correct",
        ])
        self.assertEqual(words.max_row, len(FIRST_100) + 1)
        first_word_row = [words.cell(row=2, column=c).value for c in range(1, 6)]
        self.assertEqual(first_word_row[0], FIRST_100[0])
        self.assertEqual(first_word_row[1], "Known")

    def test_session_history_and_word_detail(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        db.record_session(
            self.conn, child_id, "01/01/2026",
            [(FIRST_100[0], True), (FIRST_100[1], False)],
            time_seconds=50, correct_count=4, error_count=1, notes="good",
        )
        path = self._path()
        export_child_report(self.conn, child_id, path)

        wb = load_workbook(path)
        history = wb["Session History"]
        self.assertEqual(history.cell(row=2, column=1).value, "01/01/2026")
        self.assertEqual(history.cell(row=2, column=2).value, 50)
        self.assertEqual(history.cell(row=2, column=5).value, "good")

        detail = wb["Session Word Detail"]
        rows = {detail.cell(row=r, column=2).value: detail.cell(row=r, column=3).value for r in (2, 3)}
        self.assertEqual(rows[FIRST_100[0]], "Correct")
        self.assertEqual(rows[FIRST_100[1]], "Wrong")

    def test_empty_history_still_produces_sheets(self):
        child_id = db.add_child(self.conn, "Alex", "Year 1", "first100", set())
        path = self._path()
        export_child_report(self.conn, child_id, path)

        wb = load_workbook(path)
        self.assertEqual(wb["Session History"].cell(row=2, column=1).value, "No results recorded yet.")
        self.assertEqual(wb["Session Word Detail"].cell(row=2, column=1).value, "No results recorded yet.")


if __name__ == "__main__":
    unittest.main()
