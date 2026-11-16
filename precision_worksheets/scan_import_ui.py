"""Qt dialog that walks through reading a scanned "known words" checklist
(checklist_sheet.py / omr.py) back into the app: pick a scanned image (or
PDF) for each page, read them, and hand the resulting known-word set back
to the Add Child screen so it can tick those boxes for review."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from . import checklist_sheet, omr

FILE_FILTER = "Scans (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.pdf)"
PDF_FILTER = "PDF files (*.pdf)"


class ScanImportDialog(QDialog):
    def __init__(self, parent, tier_key: str):
        super().__init__(parent)
        self.tier_key = tier_key
        self.pages = checklist_sheet.paginate(tier_key)
        # Each page's source is either a plain image/PDF file (page_number
        # always 1) or one page of a single multi-page PDF shared across
        # several slots (page_number > 1 picks out that page within it).
        self.sources: dict[int, tuple[str, int]] = {}
        self.status_labels: dict[int, QLabel] = {}
        self.result_known_words: set[str] | None = None

        self.setWindowTitle("Import from a scanned checklist")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Choose the scanned image or PDF for each page below, then click “Read scans”.\n"
            "Print a blank checklist first from the Add Child screen if you haven't yet.",
        ))

        if len(self.pages) > 1:
            pdf_row = QHBoxLayout()
            pdf_row.addWidget(QLabel(
                "If your scanner saved every page into one PDF, you can fill them all in at once:"
            ), 1)
            pdf_btn = QPushButton("Use one PDF for all pages...")
            pdf_btn.clicked.connect(self._browse_combined_pdf)
            pdf_row.addWidget(pdf_btn)
            layout.addLayout(pdf_row)

        for page in self.pages:
            row = QHBoxLayout()
            words = page.words
            label = QLabel(f"Page {page.page_index} of {page.total_pages}  ({words[0]} … {words[-1]})")
            row.addWidget(label, 1)

            status = QLabel("Not chosen")
            status.setObjectName("MutedLabel")
            self.status_labels[page.page_index] = status
            row.addWidget(status)

            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda _checked=False, idx=page.page_index: self._browse_page(idx))
            row.addWidget(browse_btn)

            layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        read_btn = QPushButton("Read scans")
        read_btn.setObjectName("AccentButton")
        read_btn.clicked.connect(self._process)
        buttons.addWidget(read_btn)
        layout.addLayout(buttons)

    def _browse_page(self, page_index: int) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"Scan for page {page_index}", "", FILE_FILTER)
        if not path:
            return
        self.sources[page_index] = (path, 1)
        self.status_labels[page_index].setText(os.path.basename(path))

    def _browse_combined_pdf(self) -> None:
        from .app import show_error

        path, _ = QFileDialog.getOpenFileName(self, "PDF covering every page", "", PDF_FILTER)
        if not path:
            return
        try:
            page_count = len(omr.load_pdf_pages(path))
        except Exception as exc:
            show_error(self, "Couldn't open that PDF", str(exc))
            return

        filled = 0
        for page in self.pages:
            if page.page_index <= page_count:
                self.sources[page.page_index] = (path, page.page_index)
                self.status_labels[page.page_index].setText(f"{os.path.basename(path)} (page {page.page_index})")
                filled += 1
        if filled < len(self.pages):
            show_error(
                self, "PDF has fewer pages than expected",
                f"That PDF has {page_count} page(s), but this checklist needs {len(self.pages)}. "
                "Filled in what it could - please browse for the rest individually.",
            )

    def _process(self) -> None:
        from .app import show_error

        if not self.sources:
            show_error(self, "No scans chosen", "Please choose at least one scanned page first.")
            return

        known: set[str] = set()
        for page in self.pages:
            source = self.sources.get(page.page_index)
            if source is None:
                continue
            path, page_number = source
            try:
                image = omr.load_page_image(path, page_number)
                result = omr.read_page(image, page)
            except (omr.OmrError, OSError) as exc:
                show_error(self, f"Couldn't read page {page.page_index}", str(exc))
                return
            known.update(word for word, ticked in result.words.items() if ticked)

        self.result_known_words = known
        self.accept()
