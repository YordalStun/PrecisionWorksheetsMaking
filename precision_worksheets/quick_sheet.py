"""The original one-off, type-your-own-5-words generator (PySide6 / Qt
edition) - still reachable from the tracking app's home screen for a
quick sheet that doesn't need a tracked child."""

from __future__ import annotations

import datetime
import os
import re
import sys

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .app import _open_folder, ask_yes_no, show_error
from .games.adventure_boards import THEMES, build_adventure_boards, export_adventure_docx, export_adventure_pdf
from .games.bingo import build_bingo_cards, export_bingo_docx, export_bingo_pdf
from .games.pairs_cards import build_pairs_card_sheet, export_pairs_cards_docx, export_pairs_cards_pdf
from .games.snakes_and_ladders import build_board, export_board_docx, export_board_pdf
from .games.word_search import build_word_search, export_word_search_docx, export_word_search_pdf
from .games.word_trail import build_word_trail, export_word_trail_docx, export_word_trail_pdf
from .generator import build_probe_sheets
from .large_print import build_large_print_pages, export_large_print_docx, export_large_print_pdf
from .pdf_export import export_pdf
from .docx_export import export_docx

DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "PrecisionWorksheets")
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def _safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "worksheet"


class QuickSheetScreen(QWidget):
    def __init__(self, on_back):
        super().__init__()
        self.on_back = on_back

        outer = QVBoxLayout(self)
        outer.setSpacing(12)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(on_back)
        back_row = QHBoxLayout()
        back_row.addWidget(back_btn)
        back_row.addStretch(1)
        outer.addLayout(back_row)

        title = QLabel("Quick One-off Sheet")
        title.setObjectName("HeaderLabel")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll, 1)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(12)
        scroll.setWidget(body)

        self._build_child_section(layout)
        self._build_generate_all_section(layout)
        self._build_activity_tabs(layout)
        self._build_output_section(layout)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #2a6b2a;")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_child_section(self, layout: QVBoxLayout) -> None:
        box = QGroupBox("Child and words")
        grid = QGridLayout(box)

        grid.addWidget(QLabel("Child's first name:"), 0, 0)
        self.name_edit = QLineEdit()
        grid.addWidget(self.name_edit, 0, 1, 1, 4)

        grid.addWidget(QLabel("Date:"), 1, 0)
        self.date_edit = QLineEdit(datetime.date.today().strftime("%d/%m/%Y"))
        self.date_edit.setFixedWidth(110)
        grid.addWidget(self.date_edit, 1, 1)

        grid.addWidget(QLabel("5 words to practise:"), 2, 0, 1, 5)
        self.word_edits: list[QLineEdit] = []
        for i in range(5):
            grid.addWidget(QLabel(f"Word {i + 1}"), 3, i)
            edit = QLineEdit()
            edit.setFixedWidth(90)
            self.word_edits.append(edit)
            grid.addWidget(edit, 4, i)

        formats = QHBoxLayout()
        formats.addWidget(QLabel("Create:"))
        self.make_pdf_box = QCheckBox("PDF")
        self.make_pdf_box.setChecked(True)
        formats.addWidget(self.make_pdf_box)
        self.make_docx_box = QCheckBox("Word document (.docx)")
        self.make_docx_box.setChecked(True)
        formats.addWidget(self.make_docx_box)
        formats.addStretch(1)
        grid.addLayout(formats, 5, 0, 1, 5)

        layout.addWidget(box)

    def _build_generate_all_section(self, layout: QVBoxLayout) -> None:
        box = QGroupBox("Generate everything at once")
        inner = QVBoxLayout(box)
        inner.addWidget(QLabel(
            "One click: all 8 sheets, all on A4 paper, saved to the folder below\n"
            "(using each tab's current settings, e.g. number of probe sheets or bingo cards)."
        ))
        btn = QPushButton("Generate ALL sheets")
        btn.setObjectName("AccentButton")
        btn.clicked.connect(self._on_generate_all)
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn)
        btn_row.addStretch(1)
        inner.addLayout(btn_row)
        layout.addWidget(box)

    def _build_activity_tabs(self, layout: QVBoxLayout) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_probe_sheet_tab(), "Probe Sheets")
        tabs.addTab(self._build_pairs_tab(), "Matching Pairs Game")
        tabs.addTab(self._build_snakes_tab(), "Snakes && Ladders")
        tabs.addTab(self._build_bingo_tab(), "Bingo")
        tabs.addTab(self._build_word_search_tab(), "Word Search")
        tabs.addTab(self._build_word_trail_tab(), "Word Trail")
        tabs.addTab(self._build_adventure_tab(), "Adventure Boards")
        tabs.addTab(self._build_large_print_tab(), "Large Print Words")
        layout.addWidget(tabs)

    def _build_probe_sheet_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.addWidget(QLabel(
            "A fluency practice grid: the child reads through repeated,\n"
            "shuffled words against the clock."
        ), 0, 0, 1, 6)

        grid.addWidget(QLabel("Number of sheets to print:"), 1, 0)
        self.sheets_spin = QSpinBox()
        self.sheets_spin.setRange(1, 50)
        self.sheets_spin.setValue(5)
        grid.addWidget(self.sheets_spin, 1, 1)

        grid.addWidget(QLabel("Grid rows:"), 1, 2)
        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(3, 25)
        self.rows_spin.setValue(4)
        grid.addWidget(self.rows_spin, 1, 3)

        grid.addWidget(QLabel("Grid columns:"), 1, 4)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(3, 15)
        self.cols_spin.setValue(5)
        grid.addWidget(self.cols_spin, 1, 5)

        grid.addWidget(QLabel("Max word size:"), 2, 0)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 96)
        self.font_size_spin.setValue(20)
        grid.addWidget(self.font_size_spin, 2, 1)

        self.show_word_list_box = QCheckBox("Show the word list at the top of each sheet")
        self.show_word_list_box.setChecked(True)
        grid.addWidget(self.show_word_list_box, 3, 0, 1, 6)

        self.show_tracker_box = QCheckBox(
            "Include a progress tracker (Date/Score, 10 tries) at the bottom of each sheet"
        )
        self.show_tracker_box.setChecked(True)
        grid.addWidget(self.show_tracker_box, 4, 0, 1, 6)

        btn = QPushButton("Generate probe sheets")
        btn.clicked.connect(self._on_generate_probe_sheets)
        grid.addWidget(btn, 5, 0, 1, 2)
        grid.setRowStretch(6, 1)
        return tab

    def _simple_tab(self, description: str, button_text: str, on_click) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel(description))
        btn = QPushButton(button_text)
        btn.clicked.connect(on_click)
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addStretch(1)
        return tab

    def _build_pairs_tab(self) -> QWidget:
        return self._simple_tab(
            "Big cut-out cards, each word appearing twice - shuffle them\n"
            "face down and take turns flipping two to find a match.",
            "Generate matching pairs cards", self._on_generate_pairs_cards,
        )

    def _build_snakes_tab(self) -> QWidget:
        return self._simple_tab(
            "A full board with ladders, snakes, and word squares -\n"
            "land on one and read it out loud for a bonus roll.",
            "Generate Snakes && Ladders board", self._on_generate_snakes_and_ladders,
        )

    def _build_bingo_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.addWidget(QLabel(
            "Each card has a shuffled 4x4 grid of the 5 words. Call out\n"
            "words one at a time - first to complete a line shouts BINGO!"
        ), 0, 0, 1, 2)

        grid.addWidget(QLabel("Number of cards to print:"), 1, 0)
        self.bingo_cards_spin = QSpinBox()
        self.bingo_cards_spin.setRange(1, 30)
        self.bingo_cards_spin.setValue(4)
        grid.addWidget(self.bingo_cards_spin, 1, 1)

        btn = QPushButton("Generate bingo cards")
        btn.clicked.connect(self._on_generate_bingo)
        grid.addWidget(btn, 2, 0, 1, 2)
        grid.setRowStretch(3, 1)
        return tab

    def _build_word_search_tab(self) -> QWidget:
        return self._simple_tab(
            "The 5 words hidden in a grid of letters - find and circle\n"
            "them going across, down, or diagonally.",
            "Generate word search", self._on_generate_word_search,
        )

    def _build_word_trail_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.addWidget(QLabel(
            "A winding path of word circles from Start to Finish -\n"
            "read each word aloud as you make your way along the trail."
        ), 0, 0, 1, 2)

        grid.addWidget(QLabel("Paper size:"), 1, 0)
        sizes = QHBoxLayout()
        self.trail_a4_radio = QRadioButton("A4")
        self.trail_a4_radio.setChecked(True)
        self.trail_a3_radio = QRadioButton("A3 (bigger)")
        sizes.addWidget(self.trail_a4_radio)
        sizes.addWidget(self.trail_a3_radio)
        sizes.addStretch(1)
        grid.addLayout(sizes, 1, 1)

        btn = QPushButton("Generate word trail")
        btn.clicked.connect(self._on_generate_word_trail)
        grid.addWidget(btn, 2, 0, 1, 2)
        grid.setRowStretch(3, 1)
        return tab

    def _build_adventure_tab(self) -> QWidget:
        tab = QWidget()
        grid = QGridLayout(tab)
        grid.addWidget(QLabel(
            "Colourful roll-and-read board games: a winding path of word spaces\n"
            "from START to FINISH, with bonus and oops spaces along the way.\n"
            "Every board comes out different - print a few and race!"
        ), 0, 0, 1, 2)

        grid.addWidget(QLabel("Theme:"), 1, 0)
        self.adventure_theme_combo = QComboBox()
        self.adventure_theme_combo.addItem("A mix of all the themes", "mix")
        self.adventure_theme_combo.addItem("Surprise me (random)", "random")
        for key, info in THEMES.items():
            self.adventure_theme_combo.addItem(info.title, key)
        grid.addWidget(self.adventure_theme_combo, 1, 1)

        grid.addWidget(QLabel("Number of boards:"), 2, 0)
        self.adventure_count_spin = QSpinBox()
        self.adventure_count_spin.setRange(1, 20)
        self.adventure_count_spin.setValue(4)
        grid.addWidget(self.adventure_count_spin, 2, 1)

        btn = QPushButton("Generate adventure boards")
        btn.clicked.connect(self._on_generate_adventure_boards)
        grid.addWidget(btn, 3, 0, 1, 2)
        grid.setRowStretch(4, 1)
        return tab

    def _build_large_print_tab(self) -> QWidget:
        return self._simple_tab(
            "Each word alone, as big as possible, one per landscape\n"
            "page - handy for holding up or for a child who needs bigger print.",
            "Generate large print words", self._on_generate_large_print,
        )

    def _build_output_section(self, layout: QVBoxLayout) -> None:
        box = QGroupBox("Save to")
        row = QHBoxLayout(box)
        self.output_edit = QLineEdit(DEFAULT_OUTPUT_DIR)
        row.addWidget(self.output_edit, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output_dir)
        row.addWidget(browse_btn)
        layout.addWidget(box)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _browse_output_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose a folder", self.output_edit.text() or os.getcwd())
        if chosen:
            self.output_edit.setText(chosen)

    def _collect_child_and_words(self) -> tuple[str, list[str], str]:
        child_name = self.name_edit.text().strip()
        if not child_name:
            raise ValueError("Please enter the child's first name.")

        words = [e.text().strip() for e in self.word_edits]
        if any(not w for w in words):
            raise ValueError("Please fill in all 5 words.")
        if len(set(w.lower() for w in words)) < len(words):
            if not ask_yes_no(
                self, "Duplicate words", "Two of the words you entered are the same. Continue anyway?"
            ):
                raise ValueError("Please use 5 different words, or click Generate again to continue anyway.")

        date_str = self.date_edit.text().strip() or datetime.date.today().strftime("%d/%m/%Y")
        return child_name, words, date_str

    def _collect_output_options(self) -> tuple[bool, bool, str]:
        make_pdf = self.make_pdf_box.isChecked()
        make_docx = self.make_docx_box.isChecked()
        if not (make_pdf or make_docx):
            raise ValueError("Please tick at least one output format (PDF or Word).")
        output_dir = self.output_edit.text().strip() or DEFAULT_OUTPUT_DIR
        return make_pdf, make_docx, output_dir

    def _finish(self, written: list[str], output_dir: str) -> None:
        self.status_label.setText(f"Done! Created {len(written)} file(s) in {output_dir}")
        if ask_yes_no(
            self, "Files created",
            f"Created {len(written)} file(s):\n" + "\n".join(os.path.basename(p) for p in written)
            + "\n\nOpen the folder now?",
        ):
            _open_folder(output_dir)

    def _ensure_output_dir(self, output_dir: str) -> bool:
        try:
            os.makedirs(output_dir, exist_ok=True)
            return True
        except OSError as exc:
            show_error(self, "Can't use that folder", f"Couldn't create the output folder:\n{exc}")
            return False

    def _write_outputs(self, output_dir, base_name, make_pdf, make_docx, pdf_fn, docx_fn) -> list[str]:
        written = []
        if make_pdf:
            path = os.path.join(output_dir, base_name + ".pdf")
            pdf_fn(path)
            written.append(path)
        if make_docx:
            path = os.path.join(output_dir, base_name + ".docx")
            docx_fn(path)
            written.append(path)
        return written

    def _show_save_error(self, exc: OSError) -> None:
        show_error(
            self, "Couldn't save the file",
            f"{exc}\n\nIf the file is already open in another program, close it and try again.",
        )

    # ------------------------------------------------------------------
    # Generate everything at once
    # ------------------------------------------------------------------
    def _on_generate_all(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
            num_sheets, rows, cols, font_size = self._read_probe_sheet_options()
            num_bingo_cards = self._read_bingo_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        written: list[str] = []
        errors: list[str] = []

        def run(activity_name: str, build_fn, base_name: str, pdf_export_fn, docx_export_fn) -> None:
            try:
                result = build_fn()
            except ValueError as exc:
                errors.append(f"{activity_name}: {exc}")
                return
            try:
                written.extend(self._write_outputs(
                    output_dir, _safe_filename(base_name), make_pdf, make_docx,
                    pdf_fn=lambda path: pdf_export_fn(result, path),
                    docx_fn=lambda path: docx_export_fn(result, path),
                ))
            except OSError as exc:
                errors.append(f"{activity_name}: {exc}")

        run(
            "Probe Sheets",
            lambda: build_probe_sheets(
                child_name=child_name, words=words, num_sheets=num_sheets, rows=rows, cols=cols, date_str=date_str,
            ),
            f"{child_name}_probe_sheets",
            lambda sheets, path: export_pdf(
                sheets, path, include_word_list=self.show_word_list_box.isChecked(), grid_font_size=font_size,
                include_tracker=self.show_tracker_box.isChecked(),
            ),
            lambda sheets, path: export_docx(
                sheets, path, include_word_list=self.show_word_list_box.isChecked(), grid_font_size=font_size,
                include_tracker=self.show_tracker_box.isChecked(),
            ),
        )
        run(
            "Matching Pairs Game",
            lambda: build_pairs_card_sheet(child_name, words, date_str),
            f"{child_name}_word_pairs_game",
            export_pairs_cards_pdf, export_pairs_cards_docx,
        )
        run(
            "Snakes & Ladders",
            lambda: build_board(child_name, words),
            f"{child_name}_snakes_and_ladders",
            export_board_pdf, export_board_docx,
        )
        run(
            "Bingo",
            lambda: build_bingo_cards(child_name, words, date_str, num_cards=num_bingo_cards),
            f"{child_name}_bingo",
            export_bingo_pdf, export_bingo_docx,
        )
        run(
            "Word Search",
            lambda: build_word_search(child_name, words),
            f"{child_name}_word_search",
            export_word_search_pdf, export_word_search_docx,
        )
        run(
            "Word Trail",
            lambda: build_word_trail(child_name, words),
            f"{child_name}_word_trail",
            lambda trail, path: export_word_trail_pdf(trail, path, page_size="A4"),
            lambda trail, path: export_word_trail_docx(trail, path, page_size="A4"),
        )
        run(
            "Adventure Boards",
            lambda: build_adventure_boards(
                child_name, words, theme=self.adventure_theme_combo.currentData(),
                count=self.adventure_count_spin.value(),
            ),
            f"{child_name}_adventure_boards",
            export_adventure_pdf, export_adventure_docx,
        )
        run(
            "Large Print Words",
            lambda: build_large_print_pages(words),
            f"{child_name}_large_print_words",
            export_large_print_pdf, export_large_print_docx,
        )

        if errors:
            show_error(
                self, "Some sheets couldn't be created",
                f"Created {len(written)} file(s), but ran into trouble with:\n\n" + "\n".join(errors),
            )

        if written:
            self._finish(written, output_dir)
        else:
            self.status_label.setText("Nothing was created.")

    # ------------------------------------------------------------------
    # Probe sheets
    # ------------------------------------------------------------------
    def _read_probe_sheet_options(self) -> tuple[int, int, int, int]:
        return (
            self.sheets_spin.value(), self.rows_spin.value(), self.cols_spin.value(), self.font_size_spin.value(),
        )

    def _read_bingo_options(self) -> int:
        return self.bingo_cards_spin.value()

    def _on_generate_probe_sheets(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
            num_sheets, rows, cols, font_size = self._read_probe_sheet_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            sheets = build_probe_sheets(
                child_name=child_name, words=words, num_sheets=num_sheets, rows=rows, cols=cols, date_str=date_str,
            )
        except ValueError as exc:
            show_error(self, "Couldn't build the sheets", str(exc))
            return

        base_name = _safe_filename(f"{child_name}_probe_sheets")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_pdf(
                    sheets, path, include_word_list=self.show_word_list_box.isChecked(), grid_font_size=font_size,
                    include_tracker=self.show_tracker_box.isChecked(),
                ),
                docx_fn=lambda path: export_docx(
                    sheets, path, include_word_list=self.show_word_list_box.isChecked(), grid_font_size=font_size,
                    include_tracker=self.show_tracker_box.isChecked(),
                ),
            )
        except OSError as exc:
            self._show_save_error(exc)
            return

        self._finish(written, output_dir)

    # ------------------------------------------------------------------
    # Matching pairs game
    # ------------------------------------------------------------------
    def _on_generate_pairs_cards(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            sheet = build_pairs_card_sheet(child_name, words, date_str)
        except ValueError as exc:
            show_error(self, "Couldn't build the cards", str(exc))
            return

        base_name = _safe_filename(f"{child_name}_word_pairs_game")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_pairs_cards_pdf(sheet, path),
                docx_fn=lambda path: export_pairs_cards_docx(sheet, path),
            )
        except OSError as exc:
            self._show_save_error(exc)
            return

        self._finish(written, output_dir)

    # ------------------------------------------------------------------
    # Snakes & Ladders
    # ------------------------------------------------------------------
    def _on_generate_snakes_and_ladders(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            board = build_board(child_name, words)
        except ValueError as exc:
            show_error(self, "Couldn't build the board", str(exc))
            return

        base_name = _safe_filename(f"{child_name}_snakes_and_ladders")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_board_pdf(board, path),
                docx_fn=lambda path: export_board_docx(board, path),
            )
        except OSError as exc:
            self._show_save_error(exc)
            return

        self._finish(written, output_dir)

    # ------------------------------------------------------------------
    # Bingo
    # ------------------------------------------------------------------
    def _on_generate_bingo(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
            num_cards = self._read_bingo_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            cards = build_bingo_cards(child_name, words, date_str, num_cards=num_cards)
        except ValueError as exc:
            show_error(self, "Couldn't build the cards", str(exc))
            return

        base_name = _safe_filename(f"{child_name}_bingo")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_bingo_pdf(cards, path),
                docx_fn=lambda path: export_bingo_docx(cards, path),
            )
        except OSError as exc:
            self._show_save_error(exc)
            return

        self._finish(written, output_dir)

    # ------------------------------------------------------------------
    # Word Search
    # ------------------------------------------------------------------
    def _on_generate_word_search(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            puzzle = build_word_search(child_name, words)
        except ValueError as exc:
            show_error(self, "Couldn't build the puzzle", str(exc))
            return

        base_name = _safe_filename(f"{child_name}_word_search")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_word_search_pdf(puzzle, path),
                docx_fn=lambda path: export_word_search_docx(puzzle, path),
            )
        except OSError as exc:
            self._show_save_error(exc)
            return

        self._finish(written, output_dir)

    # ------------------------------------------------------------------
    # Word Trail
    # ------------------------------------------------------------------
    def _on_generate_word_trail(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            trail = build_word_trail(child_name, words)
        except ValueError as exc:
            show_error(self, "Couldn't build the trail", str(exc))
            return

        page_size = "A3" if self.trail_a3_radio.isChecked() else "A4"
        base_name = _safe_filename(f"{child_name}_word_trail_{page_size}")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_word_trail_pdf(trail, path, page_size=page_size),
                docx_fn=lambda path: export_word_trail_docx(trail, path, page_size=page_size),
            )
        except OSError as exc:
            self._show_save_error(exc)
            return

        self._finish(written, output_dir)

    # ------------------------------------------------------------------
    # Adventure boards
    # ------------------------------------------------------------------
    def _on_generate_adventure_boards(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            boards = build_adventure_boards(
                child_name, words, theme=self.adventure_theme_combo.currentData(),
                count=self.adventure_count_spin.value(),
            )
        except ValueError as exc:
            show_error(self, "Couldn't build the boards", str(exc))
            return

        base_name = _safe_filename(f"{child_name}_adventure_boards")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_adventure_pdf(boards, path),
                docx_fn=lambda path: export_adventure_docx(boards, path),
            )
        except OSError as exc:
            self._show_save_error(exc)
            return

        self._finish(written, output_dir)

    # ------------------------------------------------------------------
    # Large Print Words
    # ------------------------------------------------------------------
    def _on_generate_large_print(self) -> None:
        self.status_label.setText("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            pages = build_large_print_pages(words)
        except ValueError as exc:
            show_error(self, "Couldn't build the pages", str(exc))
            return

        base_name = _safe_filename(f"{child_name}_large_print_words")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_large_print_pdf(pages, path),
                docx_fn=lambda path: export_large_print_docx(pages, path),
            )
        except OSError as exc:
            self._show_save_error(exc)
            return

        self._finish(written, output_dir)
