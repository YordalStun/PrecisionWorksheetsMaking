"""The main per-child word-tracking app (PySide6 / Qt edition).

A home screen listing every child, an "Add Child" wizard that seeds their
starting word list from an initial checklist, and a per-child screen that
generates sheets from whichever 5 words the tracking data says are due,
then lets you log a week's results back in. The original one-off,
type-your-own-5-words generator (precision_worksheets.quick_sheet) is
still reachable from the home screen for a quick sheet that doesn't need
a tracked child.
"""

from __future__ import annotations

import datetime
import os
import random
import re
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import db
from .data.word_lists import TIERS, TIERS_BY_KEY
from .docx_export import export_docx
from .games.pairs_cards import build_pairs_card_sheet, export_pairs_cards_docx, export_pairs_cards_pdf
from .games.word_trail import build_word_trail, export_word_trail_docx, export_word_trail_pdf
from .generator import build_probe_sheets
from .pdf_export import export_pdf
from .style import STYLESHEET

DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "PrecisionWorksheets")
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
CHECKLIST_COLUMNS = 5


def _safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "child"


def _open_folder(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except OSError:
        pass


# ----------------------------------------------------------------------
# Message-box helpers, kept as module-level functions so tests can patch
# them instead of fighting a real modal event loop.
# ----------------------------------------------------------------------
def show_error(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)


def show_info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def ask_yes_no(parent: QWidget, title: str, text: str) -> bool:
    answer = QMessageBox.question(parent, title, text, QMessageBox.Yes | QMessageBox.No)
    return answer == QMessageBox.Yes


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)
    return line


class MainWindow(QMainWindow):
    """Owns the window and swaps a single content widget between screens,
    so navigating around feels like one app rather than a pile of popups."""

    def __init__(self, db_path: str | None = None):
        super().__init__()
        self.setWindowTitle("Precision Worksheet Maker")
        self.resize(1050, 760)
        self.setMinimumSize(860, 620)
        self.setStyleSheet(STYLESHEET)

        self.conn = db.connect(db_path)

        host = QWidget()
        host.setObjectName("ContentHost")
        self._layout = QVBoxLayout(host)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self.setCentralWidget(host)

        self.page: QWidget | None = None
        self.show_children_list()

    def _set_page(self, widget: QWidget) -> None:
        if self.page is not None:
            self._layout.removeWidget(self.page)
            self.page.setParent(None)
            self.page.deleteLater()
        self.page = widget
        self._layout.addWidget(widget)

    def show_children_list(self) -> None:
        self._set_page(
            ChildrenListScreen(
                self.conn,
                on_open_child=self.show_child,
                on_add_child=self.show_add_child,
                on_quick_sheet=self.open_quick_sheet,
            )
        )

    def show_add_child(self) -> None:
        self._set_page(AddChildScreen(self.conn, on_done=self.show_children_list, on_cancel=self.show_children_list))

    def show_child(self, child_id: int) -> None:
        self._set_page(ChildScreen(self.conn, child_id, on_back=self.show_children_list))

    def open_quick_sheet(self) -> None:
        from .quick_sheet import QuickSheetScreen

        self._set_page(QuickSheetScreen(on_back=self.show_children_list))


class ChildrenListScreen(QWidget):
    def __init__(self, conn, on_open_child, on_add_child, on_quick_sheet):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Children")
        title.setObjectName("HeaderLabel")
        header.addWidget(title)
        header.addStretch(1)

        add_btn = QPushButton("+ Add Child")
        add_btn.setObjectName("AccentButton")
        add_btn.clicked.connect(on_add_child)
        header.addWidget(add_btn)

        quick_btn = QPushButton("Quick one-off sheet (no tracking)")
        quick_btn.clicked.connect(on_quick_sheet)
        header.addWidget(quick_btn)
        layout.addLayout(header)

        children = db.list_children(conn)
        if not children:
            empty = QLabel('No children yet - click "+ Add Child" to get started.')
            empty.setObjectName("MutedLabel")
            layout.addWidget(empty)
            layout.addStretch(1)
            return

        table = QTableWidget(len(children), 5)
        table.setHorizontalHeaderLabels(["Name", "Year group", "Current word list", "Progress", ""])
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(44)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.horizontalHeader().setStretchLastSection(False)
        table.setColumnWidth(3, 230)
        table.setColumnWidth(4, 100)

        for r, child in enumerate(children):
            tier = TIERS_BY_KEY[child["current_tier"]]
            known = len(db.known_words(conn, child["id"], tier.key))
            total = len(tier.words)

            table.setItem(r, 0, QTableWidgetItem(child["name"]))
            table.setItem(r, 1, QTableWidgetItem(child["year_group"] or ""))
            table.setItem(r, 2, QTableWidgetItem(tier.label))
            table.setCellWidget(r, 3, _progress_cell(known, total))

            open_btn = QPushButton("Open")
            open_btn.clicked.connect(lambda _checked=False, cid=child["id"]: on_open_child(cid))
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.addWidget(open_btn)
            table.setCellWidget(r, 4, cell)

        header_view = table.horizontalHeader()
        header_view.setSectionResizeMode(0, header_view.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, header_view.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, header_view.ResizeMode.Stretch)
        header_view.setSectionResizeMode(3, header_view.ResizeMode.Fixed)
        header_view.setSectionResizeMode(4, header_view.ResizeMode.Fixed)

        layout.addWidget(table, 1)


def _progress_cell(known: int, total: int) -> QWidget:
    cell = QWidget()
    row = QHBoxLayout(cell)
    row.setContentsMargins(4, 2, 4, 2)
    row.setSpacing(8)

    bar = QProgressBar()
    bar.setRange(0, max(total, 1))
    bar.setValue(known)
    bar.setTextVisible(False)
    bar.setFixedWidth(90)
    row.addWidget(bar)

    label = QLabel(f"{known} / {total} known")
    row.addWidget(label)
    return cell


class AddChildScreen(QWidget):
    def __init__(self, conn, on_done, on_cancel):
        super().__init__()
        self.conn = conn
        self.on_done = on_done
        self.checklist_boxes: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("Add a Child")
        title.setObjectName("HeaderLabel")
        layout.addWidget(title)

        form = QHBoxLayout()
        form.addWidget(QLabel("Child's name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setFixedWidth(220)
        form.addWidget(self.name_edit)
        form.addSpacing(24)
        form.addWidget(QLabel("Year group:"))
        self.year_edit = QLineEdit()
        self.year_edit.setFixedWidth(120)
        form.addWidget(self.year_edit)
        form.addStretch(1)
        layout.addLayout(form)

        layout.addWidget(QLabel("Which word list are they currently on?"))
        tier_row = QHBoxLayout()
        self.tier_group = QButtonGroup(self)
        self.tier_buttons: dict[str, QRadioButton] = {}
        for i, tier in enumerate(TIERS):
            radio = QRadioButton(tier.label)
            if i == 0:
                radio.setChecked(True)
            radio.toggled.connect(lambda checked, t=tier.key: checked and self._rebuild_checklist(t))
            self.tier_group.addButton(radio)
            self.tier_buttons[tier.key] = radio
            tier_row.addWidget(radio)
        tier_row.addStretch(1)
        layout.addLayout(tier_row)

        hint = QLabel(
            "Tick every word they already know from that list - everything left unticked\n"
            "is what the app will start introducing, in list order."
        )
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)

        self.checklist_area = QScrollArea()
        self.checklist_area.setWidgetResizable(True)
        layout.addWidget(self.checklist_area, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(on_cancel)
        buttons.addWidget(cancel_btn)
        add_btn = QPushButton("Add child")
        add_btn.setObjectName("AccentButton")
        add_btn.clicked.connect(self._submit)
        buttons.addWidget(add_btn)
        layout.addLayout(buttons)

        self._rebuild_checklist(TIERS[0].key)

    def _current_tier_key(self) -> str:
        for key, radio in self.tier_buttons.items():
            if radio.isChecked():
                return key
        return TIERS[0].key

    def _rebuild_checklist(self, tier_key: str) -> None:
        self.checklist_boxes = {}
        tier = TIERS_BY_KEY[tier_key]

        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(2)
        for i, word in enumerate(tier.words):
            box = QCheckBox(word)
            self.checklist_boxes[word] = box
            row, col = divmod(i, CHECKLIST_COLUMNS)
            grid.addWidget(box, row, col)
        grid.setColumnStretch(CHECKLIST_COLUMNS, 1)

        self.checklist_area.setWidget(inner)

    def _submit(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            show_error(self, "Check your details", "Please enter the child's name.")
            return
        known = {word for word, box in self.checklist_boxes.items() if box.isChecked()}
        try:
            db.add_child(self.conn, name, self.year_edit.text(), self._current_tier_key(), known)
        except ValueError as exc:
            show_error(self, "Couldn't add child", str(exc))
            return
        self.on_done()


class ChildScreen(QWidget):
    def __init__(self, conn, child_id: int, on_back):
        super().__init__()
        self.conn = conn
        self.child_id = child_id
        self.on_back = on_back
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.current_words: list[str] = []

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(12)
        self._build()

    def _child(self):
        return db.get_child(self.conn, self.child_id)

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _build(self) -> None:
        self._clear()

        child = self._child()
        if child is None:
            self._layout.addWidget(QLabel("This child no longer exists."))
            back_btn = QPushButton("Back to children")
            back_btn.clicked.connect(self.on_back)
            self._layout.addWidget(back_btn)
            self._layout.addStretch(1)
            return

        tier = TIERS_BY_KEY[child["current_tier"]]
        known = len(db.known_words(self.conn, self.child_id, tier.key))
        total = len(tier.words)

        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(self.on_back)
        back_row = QHBoxLayout()
        back_row.addWidget(back_btn)
        back_row.addStretch(1)
        self._layout.addLayout(back_row)

        name_label = QLabel(child["name"])
        name_label.setObjectName("HeaderLabel")
        self._layout.addWidget(name_label)

        subtitle = f"{child['year_group'] or 'No year group set'}  ·  {tier.label}  ·  {known} / {total} known"
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("MutedLabel")
        self._layout.addWidget(subtitle_label)

        tabs = QTabWidget()
        tabs.addTab(self._build_sheets_tab(), "This Week's Sheets")
        tabs.addTab(self._build_games_tab(), "Games")
        tabs.addTab(self._build_history_tab(), "History")
        self._layout.addWidget(tabs, 1)

    # ------------------------------------------------------------------
    # Sheets tab
    # ------------------------------------------------------------------
    def _build_sheets_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        self.current_words = db.choose_session_words(self.conn, self.child_id, rng=random.Random())

        words_box = QGroupBox("Next sheet will use")
        words_layout = QVBoxLayout(words_box)
        self.words_label = QLabel()
        self.words_label.setStyleSheet("font-size: 12pt;")
        words_layout.addWidget(self.words_label)
        self._refresh_words_label()

        explainer = QLabel(
            "The 3 practice words are picked automatically (struggling words first, then\n"
            "the next new ones) - only the 2 known words are random, so you can reshuffle those."
        )
        explainer.setObjectName("MutedLabel")
        words_layout.addWidget(explainer)

        shuffle_btn = QPushButton("\U0001f500 Shuffle known words")
        shuffle_btn.clicked.connect(self._shuffle_known)
        shuffle_row = QHBoxLayout()
        shuffle_row.addWidget(shuffle_btn)
        shuffle_row.addStretch(1)
        words_layout.addLayout(shuffle_row)
        layout.addWidget(words_box)

        output_box = QGroupBox("Save to")
        output_layout = QHBoxLayout(output_box)
        self.output_edit = QLineEdit(self.output_dir)
        self.output_edit.textChanged.connect(self._on_output_dir_changed)
        output_layout.addWidget(self.output_edit, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output_dir)
        output_layout.addWidget(browse_btn)
        layout.addWidget(output_box)

        generate_btn = QPushButton("Generate sheets (probe sheet, word trail, matching pairs)")
        generate_btn.setObjectName("AccentButton")
        generate_btn.clicked.connect(self._generate_sheets)
        pairs_btn = QPushButton("\U0001f0cf Just the pairs sheet")
        pairs_btn.clicked.connect(self._generate_pairs_only)
        export_btn = QPushButton("\U0001f4ca Export to Excel")
        export_btn.clicked.connect(self._export_excel)
        gen_row = QHBoxLayout()
        gen_row.addWidget(generate_btn)
        gen_row.addWidget(pairs_btn)
        gen_row.addWidget(export_btn)
        gen_row.addStretch(1)
        layout.addLayout(gen_row)

        layout.addWidget(_hline())

        record_btn = QPushButton("Record this week's results →")
        record_btn.setObjectName("AccentButton")
        record_btn.clicked.connect(self._open_record_dialog)
        record_row = QHBoxLayout()
        record_row.addWidget(record_btn)
        record_row.addStretch(1)
        layout.addLayout(record_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #2a6b2a;")
        layout.addWidget(self.status_label)

        layout.addStretch(1)
        return tab

    def _refresh_words_label(self) -> None:
        practice, known = self.current_words[:3], self.current_words[3:]
        self.words_label.setText(
            "Practising: " + ", ".join(practice) + "   ·   Known: " + ", ".join(known)
        )

    def _shuffle_known(self) -> None:
        tier_key = self._child()["current_tier"]
        known_pool = db.all_known_words(self.conn, self.child_id, tier_key)
        from .tracking import pick_known_words

        self.current_words = self.current_words[:3] + pick_known_words(known_pool, random.Random())
        self._refresh_words_label()

    def _on_output_dir_changed(self, text: str) -> None:
        self.output_dir = text

    def _browse_output_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose a folder", self.output_edit.text() or os.getcwd())
        if chosen:
            self.output_edit.setText(chosen)

    def _generate_sheets(self) -> None:
        child = self._child()
        output_dir = os.path.join(
            self.output_edit.text().strip() or DEFAULT_OUTPUT_DIR, _safe_filename(child["name"])
        )
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            show_error(self, "Can't use that folder", f"Couldn't create the output folder:\n{exc}")
            return

        words = list(self.current_words)
        date_str = datetime.date.today().strftime("%d/%m/%Y")
        base = _safe_filename(child["name"])

        try:
            sheets = build_probe_sheets(
                child_name=child["name"], words=words, num_sheets=1, rows=4, cols=5, date_str=date_str
            )
            export_pdf(sheets, os.path.join(output_dir, f"{base}_probe_sheet.pdf"))
            export_docx(sheets, os.path.join(output_dir, f"{base}_probe_sheet.docx"))

            trail = build_word_trail(child["name"], words)
            export_word_trail_pdf(trail, os.path.join(output_dir, f"{base}_word_trail.pdf"), page_size="A4")
            export_word_trail_docx(trail, os.path.join(output_dir, f"{base}_word_trail.docx"), page_size="A4")

            pairs = build_pairs_card_sheet(child["name"], words, date_str)
            export_pairs_cards_pdf(pairs, os.path.join(output_dir, f"{base}_matching_pairs.pdf"))
            export_pairs_cards_docx(pairs, os.path.join(output_dir, f"{base}_matching_pairs.docx"))
        except (ValueError, OSError) as exc:
            show_error(self, "Couldn't generate the sheets", str(exc))
            return

        db.set_last_sheet(self.conn, self.child_id, words, date_str)
        self.status_label.setText(f"Done! 6 files saved in {output_dir}")
        if ask_yes_no(self, "Sheets created", "Sheets created. Open the folder now?"):
            _open_folder(output_dir)

    def _generate_pairs_only(self) -> None:
        child = self._child()
        output_dir = os.path.join(
            self.output_edit.text().strip() or DEFAULT_OUTPUT_DIR, _safe_filename(child["name"])
        )
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            show_error(self, "Can't use that folder", f"Couldn't create the output folder:\n{exc}")
            return

        words = list(self.current_words)
        date_str = datetime.date.today().strftime("%d/%m/%Y")
        base = _safe_filename(child["name"])

        try:
            pairs = build_pairs_card_sheet(child["name"], words, date_str)
            export_pairs_cards_pdf(pairs, os.path.join(output_dir, f"{base}_matching_pairs.pdf"))
            export_pairs_cards_docx(pairs, os.path.join(output_dir, f"{base}_matching_pairs.docx"))
        except (ValueError, OSError) as exc:
            show_error(self, "Couldn't generate the pairs sheet", str(exc))
            return

        self.status_label.setText(f"Done! Pairs sheet saved in {output_dir}")
        if ask_yes_no(self, "Pairs sheet created", "Pairs sheet created. Open the folder now?"):
            _open_folder(output_dir)

    # ------------------------------------------------------------------
    # Games tab
    # ------------------------------------------------------------------
    def _build_games_tab(self) -> QWidget:
        from .games_ui import GamesTab

        return GamesTab(self, self.conn, self.child_id, self.current_words)

    def _export_excel(self) -> None:
        from .excel_export import export_child_report

        child = self._child()
        output_dir = self.output_edit.text().strip() or DEFAULT_OUTPUT_DIR
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            show_error(self, "Can't use that folder", f"Couldn't create the output folder:\n{exc}")
            return

        path = os.path.join(output_dir, f"{_safe_filename(child['name'])}_report.xlsx")
        try:
            export_child_report(self.conn, self.child_id, path)
        except (ValueError, OSError) as exc:
            show_error(self, "Couldn't export the report", str(exc))
            return

        self.status_label.setText(f"Done! Report saved to {path}")
        if ask_yes_no(self, "Report exported", "Excel report created. Open the folder now?"):
            _open_folder(output_dir)

    # ------------------------------------------------------------------
    # Record results
    # ------------------------------------------------------------------
    def _open_record_dialog(self) -> None:
        words = db.get_last_sheet_words(self.conn, self.child_id) or self.current_words
        dlg = RecordResultsDialog(self, self.conn, self.child_id, words, on_saved=self._on_recorded)
        dlg.exec()

    def _on_recorded(self) -> None:
        self._build()

    # ------------------------------------------------------------------
    # History tab
    # ------------------------------------------------------------------
    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)

        sessions = db.get_sessions(self.conn, self.child_id)
        if not sessions:
            empty = QLabel("No results recorded yet.")
            empty.setObjectName("MutedLabel")
            layout.addWidget(empty)
            layout.addStretch(1)
            return tab

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(8)

        for session in sessions:
            card = QGroupBox(session["date"])
            card_layout = QVBoxLayout(card)

            bits = []
            if session["time_seconds"] is not None:
                bits.append(f"{session['time_seconds']}s")
            if session["correct_count"] is not None:
                bits.append(f"{session['correct_count']} correct")
            if session["error_count"] is not None:
                bits.append(f"{session['error_count']} errors")
            if bits:
                bits_label = QLabel("  ·  ".join(bits))
                bits_label.setObjectName("MutedLabel")
                card_layout.addWidget(bits_label)

            words_row = QHBoxLayout()
            for wr in db.get_session_words(self.conn, session["id"]):
                mark = "✓" if wr["correct"] else "✗"
                color = "#2a6b2a" if wr["correct"] else "#a03030"
                word_label = QLabel(f"{wr['word']} {mark}")
                word_label.setStyleSheet(f"color: {color};")
                words_row.addWidget(word_label)
            words_row.addStretch(1)
            card_layout.addLayout(words_row)

            if session["notes"]:
                notes_label = QLabel(session["notes"])
                notes_label.setWordWrap(True)
                notes_label.setObjectName("MutedLabel")
                card_layout.addWidget(notes_label)

            inner_layout.addWidget(card)

        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        layout.addWidget(scroll)
        return tab


class RecordResultsDialog(QDialog):
    def __init__(self, parent: QWidget, conn, child_id: int, words: list[str], on_saved):
        super().__init__(parent)
        self.setWindowTitle("Record this week's results")
        self.conn = conn
        self.child_id = child_id
        self.words = words
        self.on_saved = on_saved

        layout = QVBoxLayout(self)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Date:"))
        self.date_edit = QLineEdit(datetime.date.today().strftime("%d/%m/%Y"))
        self.date_edit.setFixedWidth(110)
        date_row.addWidget(self.date_edit)
        date_row.addStretch(1)
        layout.addLayout(date_row)

        layout.addWidget(QLabel("Tick each word they got right this time:"))
        self.word_boxes: dict[str, QCheckBox] = {}
        for word in words:
            box = QCheckBox(word)
            box.setChecked(True)
            self.word_boxes[word] = box
            layout.addWidget(box)

        numbers = QGridLayout()
        numbers.addWidget(QLabel("Time (seconds):"), 0, 0)
        self.time_edit = QLineEdit()
        self.time_edit.setFixedWidth(70)
        numbers.addWidget(self.time_edit, 0, 1)

        numbers.addWidget(QLabel("Correct (overall):"), 1, 0)
        self.correct_edit = QLineEdit()
        self.correct_edit.setFixedWidth(70)
        numbers.addWidget(self.correct_edit, 1, 1)

        numbers.addWidget(QLabel("Errors (overall):"), 2, 0)
        self.errors_edit = QLineEdit()
        self.errors_edit.setFixedWidth(70)
        numbers.addWidget(self.errors_edit, 2, 1)
        numbers.setColumnStretch(2, 1)
        layout.addLayout(numbers)

        layout.addWidget(QLabel("Notes:"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(70)
        layout.addWidget(self.notes_edit)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("AccentButton")
        save_btn.clicked.connect(self._submit)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    def _parse_optional_int(self, value: str, label: str) -> int | None:
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{label} must be a whole number.")

    def _submit(self) -> None:
        try:
            time_seconds = self._parse_optional_int(self.time_edit.text(), "Time")
            correct_count = self._parse_optional_int(self.correct_edit.text(), "Correct")
            error_count = self._parse_optional_int(self.errors_edit.text(), "Errors")
        except ValueError as exc:
            show_error(self, "Check your details", str(exc))
            return

        date_str = self.date_edit.text().strip() or datetime.date.today().strftime("%d/%m/%Y")
        word_results = [(word, box.isChecked()) for word, box in self.word_boxes.items()]
        notes = self.notes_edit.toPlainText().strip()

        before_tier = db.get_child(self.conn, self.child_id)["current_tier"]
        db.record_session(
            self.conn, self.child_id, date_str, word_results,
            time_seconds=time_seconds, correct_count=correct_count, error_count=error_count, notes=notes,
        )
        after = db.get_child(self.conn, self.child_id)

        self.accept()
        self.on_saved()
        if after["current_tier"] != before_tier:
            new_tier = TIERS_BY_KEY[after["current_tier"]]
            show_info(
                self.parent() or self,
                "Word list complete!",
                f"{after['name']} has learned every word on their current list and has "
                f"moved on to {new_tier.label}.",
            )


def main() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
