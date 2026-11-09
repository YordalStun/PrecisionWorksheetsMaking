"""Qt dialog that walks through reading a scanned "known words" checklist
(checklist_sheet.py / omr.py) back into the app: pick a scanned image for
each page, read them, and hand the resulting known-word set back to the
Add Child screen so it can tick those boxes for review."""

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

IMAGE_FILTER = "Scanned images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)"


class ScanImportDialog(QDialog):
    def __init__(self, parent, tier_key: str):
        super().__init__(parent)
        self.tier_key = tier_key
        self.pages = checklist_sheet.paginate(tier_key)
        self.file_paths: dict[int, str] = {}
        self.status_labels: dict[int, QLabel] = {}
        self.result_known_words: set[str] | None = None

        self.setWindowTitle("Import from a scanned checklist")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Choose the scanned image for each page below, then click “Read scans”.\n"
            "Print a blank checklist first from the Add Child screen if you haven't yet.",
        ))

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
        from .app import show_error  # local import avoids a circular import at module load time

        path, _ = QFileDialog.getOpenFileName(self, f"Scan for page {page_index}", "", IMAGE_FILTER)
        if not path:
            return
        self.file_paths[page_index] = path
        self.status_labels[page_index].setText(os.path.basename(path))

    def _process(self) -> None:
        from .app import show_error

        if not self.file_paths:
            show_error(self, "No scans chosen", "Please choose at least one scanned page first.")
            return

        known: set[str] = set()
        for page in self.pages:
            path = self.file_paths.get(page.page_index)
            if path is None:
                continue
            try:
                image = omr.load_image(path)
                result = omr.read_page(image, page)
            except (omr.OmrError, OSError) as exc:
                show_error(self, f"Couldn't read page {page.page_index}", str(exc))
                return
            known.update(word for word, ticked in result.words.items() if ticked)

        self.result_known_words = known
        self.accept()
