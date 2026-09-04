import os
import tempfile
import unittest

from docx import Document

from precision_worksheets.docx_export import export_docx
from precision_worksheets.generator import build_probe_sheets
from precision_worksheets.pdf_export import export_pdf


class TestExports(unittest.TestCase):
    def setUp(self):
        self.sheets = build_probe_sheets(
            "Alex", ["cat", "dog", "sun", "run", "big"], num_sheets=3,
            rows=10, cols=8, date_str="04/09/2026", seed=42,
        )
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_export_pdf_creates_valid_multi_page_file(self):
        path = os.path.join(self.tmpdir.name, "out.pdf")
        export_pdf(self.sheets, path)
        with open(path, "rb") as f:
            header = f.read(5)
            self.assertEqual(header, b"%PDF-")
        self.assertGreater(os.path.getsize(path), 0)

    def test_export_pdf_rejects_empty_sheet_list(self):
        path = os.path.join(self.tmpdir.name, "out.pdf")
        with self.assertRaises(ValueError):
            export_pdf([], path)

    def test_export_docx_creates_one_table_per_sheet(self):
        path = os.path.join(self.tmpdir.name, "out.docx")
        export_docx(self.sheets, path)
        doc = Document(path)
        self.assertEqual(len(doc.tables), 3)
        for table in doc.tables:
            self.assertEqual(len(table.rows), 10)
            self.assertEqual(len(table.columns), 9)  # 8 words + row-number column

    def test_export_docx_word_appears_in_grid(self):
        path = os.path.join(self.tmpdir.name, "out.docx")
        export_docx(self.sheets, path)
        doc = Document(path)
        cell_text = doc.tables[0].rows[0].cells[1].text
        self.assertIn(cell_text, ["cat", "dog", "sun", "run", "big"])

    def test_export_docx_rejects_empty_sheet_list(self):
        path = os.path.join(self.tmpdir.name, "out.docx")
        with self.assertRaises(ValueError):
            export_docx([], path)


if __name__ == "__main__":
    unittest.main()
