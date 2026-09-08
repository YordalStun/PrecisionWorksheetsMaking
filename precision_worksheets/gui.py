"""Tkinter desktop GUI for the Precision Worksheet Maker.

Tkinter ships with the standard python.org Windows installer, so this runs
on Windows with no extra install beyond `pip install -r requirements.txt`
(or as a packaged .exe - see build_windows_exe.bat).
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .docx_export import export_docx
from .games.bingo import build_bingo_cards, export_bingo_docx, export_bingo_pdf
from .games.pairs_cards import build_pairs_card_sheet, export_pairs_cards_docx, export_pairs_cards_pdf
from .games.snakes_and_ladders import build_board, export_board_docx, export_board_pdf
from .games.word_search import build_word_search, export_word_search_docx, export_word_search_pdf
from .games.word_trail import build_word_trail, export_word_trail_docx, export_word_trail_pdf
from .generator import build_probe_sheets
from .large_print import build_large_print_pages, export_large_print_docx, export_large_print_pdf
from .pdf_export import export_pdf

DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "PrecisionWorksheets")
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


class PrecisionWorksheetApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Precision Worksheet Maker")
        root.resizable(False, False)

        self.word_vars = [tk.StringVar() for _ in range(5)]
        self.name_var = tk.StringVar()
        self.date_var = tk.StringVar(value=datetime.date.today().strftime("%d/%m/%Y"))
        self.sheets_var = tk.IntVar(value=5)
        self.rows_var = tk.IntVar(value=4)
        self.cols_var = tk.IntVar(value=5)
        self.font_size_var = tk.IntVar(value=20)
        self.show_word_list_var = tk.BooleanVar(value=True)
        self.show_tracker_var = tk.BooleanVar(value=True)
        self.bingo_cards_var = tk.IntVar(value=4)
        self.trail_page_size_var = tk.StringVar(value="A4")
        self.make_pdf_var = tk.BooleanVar(value=True)
        self.make_docx_var = tk.BooleanVar(value=True)
        self.output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        self.status_var = tk.StringVar(value="")

        outer = ttk.Frame(root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")

        self._build_child_section(outer, row=0)
        self._build_generate_all_section(outer, row=1)
        self._build_activity_tabs(outer, row=2)
        self._build_output_section(outer, row=3)
        self._build_status_section(outer, row=4)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_child_section(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Child and words", padding=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Child's first name:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.name_var, width=24).grid(
            row=0, column=1, columnspan=4, sticky="w", padx=(6, 0)
        )

        ttk.Label(frame, text="Date:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(frame, textvariable=self.date_var, width=14).grid(
            row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0)
        )

        ttk.Label(frame, text="5 words to practise:").grid(
            row=2, column=0, columnspan=5, sticky="w", pady=(10, 4)
        )
        for i, var in enumerate(self.word_vars):
            ttk.Label(frame, text=f"Word {i + 1}").grid(row=3, column=i, sticky="w")
            ttk.Entry(frame, textvariable=var, width=10).grid(
                row=4, column=i, sticky="w", padx=(0, 6)
            )

        formats = ttk.Frame(frame)
        formats.grid(row=5, column=0, columnspan=5, sticky="w", pady=(12, 0))
        ttk.Label(formats, text="Create:").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(formats, text="PDF", variable=self.make_pdf_var).grid(
            row=0, column=1, sticky="w", padx=(10, 10)
        )
        ttk.Checkbutton(formats, text="Word document (.docx)", variable=self.make_docx_var).grid(
            row=0, column=2, sticky="w"
        )

    def _build_generate_all_section(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Generate everything at once", padding=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(
            frame, text="One click: all 7 sheets, all on A4 paper, saved to the folder below\n"
            "(using each tab's current settings, e.g. number of probe sheets or bingo cards).",
            justify="left",
        ).grid(row=0, column=0, sticky="w")

        style = ttk.Style()
        style.configure("GenerateAll.TButton", font=("TkDefaultFont", 11, "bold"))
        ttk.Button(
            frame, text="Generate ALL sheets", style="GenerateAll.TButton", command=self._on_generate_all,
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))

    def _build_activity_tabs(self, parent: ttk.Frame, row: int) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=row, column=0, sticky="ew", pady=(0, 10))

        notebook.add(self._build_probe_sheet_tab(notebook), text="Probe Sheets")
        notebook.add(self._build_pairs_tab(notebook), text="Matching Pairs Game")
        notebook.add(self._build_snakes_tab(notebook), text="Snakes & Ladders")
        notebook.add(self._build_bingo_tab(notebook), text="Bingo")
        notebook.add(self._build_word_search_tab(notebook), text="Word Search")
        notebook.add(self._build_word_trail_tab(notebook), text="Word Trail")
        notebook.add(self._build_large_print_tab(notebook), text="Large Print Words")

    def _build_probe_sheet_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)

        ttk.Label(
            tab, text="A fluency practice grid: the child reads through repeated,\n"
            "shuffled words against the clock.", justify="left",
        ).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 10))

        ttk.Label(tab, text="Number of sheets to print:").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(tab, from_=1, to=50, textvariable=self.sheets_var, width=6).grid(
            row=1, column=1, sticky="w", padx=(6, 24)
        )

        ttk.Label(tab, text="Grid rows:").grid(row=1, column=2, sticky="w")
        ttk.Spinbox(tab, from_=3, to=25, textvariable=self.rows_var, width=6).grid(
            row=1, column=3, sticky="w", padx=(6, 24)
        )

        ttk.Label(tab, text="Grid columns:").grid(row=1, column=4, sticky="w")
        ttk.Spinbox(tab, from_=3, to=15, textvariable=self.cols_var, width=6).grid(
            row=1, column=5, sticky="w", padx=(6, 0)
        )

        ttk.Label(tab, text="Max word size:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(tab, from_=12, to=96, textvariable=self.font_size_var, width=6).grid(
            row=2, column=1, sticky="w", padx=(6, 24), pady=(8, 0)
        )

        ttk.Checkbutton(
            tab, text="Show the word list at the top of each sheet", variable=self.show_word_list_var,
        ).grid(row=3, column=0, columnspan=6, sticky="w", pady=(10, 0))

        ttk.Checkbutton(
            tab, text="Include a progress tracker (Date/Score, 10 tries) at the bottom of each sheet",
            variable=self.show_tracker_var,
        ).grid(row=4, column=0, columnspan=6, sticky="w", pady=(4, 0))

        ttk.Button(tab, text="Generate probe sheets", command=self._on_generate_probe_sheets).grid(
            row=5, column=0, columnspan=6, sticky="w", pady=(14, 0)
        )
        return tab

    def _build_pairs_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)
        ttk.Label(
            tab, text="Big cut-out cards, each word appearing twice - shuffle them\n"
            "face down and take turns flipping two to find a match.", justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))
        ttk.Button(tab, text="Generate matching pairs cards", command=self._on_generate_pairs_cards).grid(
            row=1, column=0, sticky="w"
        )
        return tab

    def _build_snakes_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)
        ttk.Label(
            tab, text="A full board with ladders, snakes, and word squares -\n"
            "land on one and read it out loud for a bonus roll.", justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))
        ttk.Button(tab, text="Generate Snakes & Ladders board", command=self._on_generate_snakes_and_ladders).grid(
            row=1, column=0, sticky="w"
        )
        return tab

    def _build_bingo_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)
        ttk.Label(
            tab, text="Each card has a shuffled 4x4 grid of the 5 words. Call out\n"
            "words one at a time - first to complete a line shouts BINGO!", justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(tab, text="Number of cards to print:").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(tab, from_=1, to=30, textvariable=self.bingo_cards_var, width=6).grid(
            row=1, column=1, sticky="w", padx=(6, 0)
        )

        ttk.Button(tab, text="Generate bingo cards", command=self._on_generate_bingo).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(14, 0)
        )
        return tab

    def _build_word_search_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)
        ttk.Label(
            tab, text="The 5 words hidden in a grid of letters - find and circle\n"
            "them going across, down, or diagonally.", justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))
        ttk.Button(tab, text="Generate word search", command=self._on_generate_word_search).grid(
            row=1, column=0, sticky="w"
        )
        return tab

    def _build_word_trail_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)
        ttk.Label(
            tab, text="A winding path of word circles from Start to Finish -\n"
            "read each word aloud as you make your way along the trail.", justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(tab, text="Paper size:").grid(row=1, column=0, sticky="w")
        sizes = ttk.Frame(tab)
        sizes.grid(row=1, column=1, sticky="w", padx=(6, 0))
        ttk.Radiobutton(sizes, text="A4", variable=self.trail_page_size_var, value="A4").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Radiobutton(sizes, text="A3 (bigger)", variable=self.trail_page_size_var, value="A3").grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )

        ttk.Button(tab, text="Generate word trail", command=self._on_generate_word_trail).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(14, 0)
        )
        return tab

    def _build_large_print_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)
        ttk.Label(
            tab, text="Each word alone, as big as possible, one per landscape\n"
            "page - handy for holding up or for a child who needs bigger print.", justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 14))
        ttk.Button(tab, text="Generate large print words", command=self._on_generate_large_print).grid(
            row=1, column=0, sticky="w"
        )
        return tab

    def _build_output_section(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Save to", padding=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))

        ttk.Entry(frame, textvariable=self.output_dir_var, width=48).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(frame, text="Browse...", command=self._browse_output_dir).grid(
            row=0, column=1, padx=(8, 0)
        )

    def _build_status_section(self, parent: ttk.Frame, row: int) -> None:
        ttk.Label(parent, textvariable=self.status_var, foreground="#2a6b2a").grid(
            row=row, column=0, sticky="w"
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _browse_output_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_dir_var.get() or os.getcwd())
        if chosen:
            self.output_dir_var.set(chosen)

    def _collect_child_and_words(self) -> tuple[str, list[str], str]:
        """Validate and return (child_name, words, date_str) - shared by every activity."""
        child_name = self.name_var.get().strip()
        if not child_name:
            raise ValueError("Please enter the child's first name.")

        words = [v.get().strip() for v in self.word_vars]
        if any(not w for w in words):
            raise ValueError("Please fill in all 5 words.")
        if len(set(w.lower() for w in words)) < len(words):
            if not messagebox.askyesno(
                "Duplicate words",
                "Two of the words you entered are the same. Continue anyway?",
            ):
                raise ValueError("Please use 5 different words, or click Generate again to continue anyway.")

        date_str = self.date_var.get().strip() or datetime.date.today().strftime("%d/%m/%Y")
        return child_name, words, date_str

    def _collect_output_options(self) -> tuple[bool, bool, str]:
        make_pdf = self.make_pdf_var.get()
        make_docx = self.make_docx_var.get()
        if not (make_pdf or make_docx):
            raise ValueError("Please tick at least one output format (PDF or Word).")
        output_dir = self.output_dir_var.get().strip() or DEFAULT_OUTPUT_DIR
        return make_pdf, make_docx, output_dir

    def _finish(self, written: list[str], output_dir: str) -> None:
        self.status_var.set(f"Done! Created {len(written)} file(s) in {output_dir}")
        if messagebox.askyesno(
            "Files created",
            f"Created {len(written)} file(s):\n" + "\n".join(os.path.basename(p) for p in written)
            + "\n\nOpen the folder now?",
        ):
            _open_folder(output_dir)

    # ------------------------------------------------------------------
    # Generate everything at once
    # ------------------------------------------------------------------
    def _on_generate_all(self) -> None:
        self.status_var.set("")
        try:
            child_name, words, date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
            num_sheets, rows, cols, font_size = self._read_probe_sheet_options()
            num_bingo_cards = self._read_bingo_options()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
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
                sheets, path, include_word_list=self.show_word_list_var.get(), grid_font_size=font_size,
                include_tracker=self.show_tracker_var.get(),
            ),
            lambda sheets, path: export_docx(
                sheets, path, include_word_list=self.show_word_list_var.get(), grid_font_size=font_size,
                include_tracker=self.show_tracker_var.get(),
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
            "Large Print Words",
            lambda: build_large_print_pages(words),
            f"{child_name}_large_print_words",
            export_large_print_pdf, export_large_print_docx,
        )

        if errors:
            messagebox.showerror(
                "Some sheets couldn't be created",
                f"Created {len(written)} file(s), but ran into trouble with:\n\n" + "\n".join(errors),
            )

        if written:
            self._finish(written, output_dir)
        else:
            self.status_var.set("Nothing was created.")

    # ------------------------------------------------------------------
    # Probe sheets
    # ------------------------------------------------------------------
    def _read_probe_sheet_options(self) -> tuple[int, int, int, int]:
        """Returns (num_sheets, rows, cols, font_size), validated."""
        try:
            num_sheets = int(self.sheets_var.get())
            rows = int(self.rows_var.get())
            cols = int(self.cols_var.get())
            font_size = int(self.font_size_var.get())
        except (tk.TclError, ValueError):
            raise ValueError("Sheets, rows, columns and max word size must be whole numbers.")
        if not (1 <= num_sheets <= 50):
            raise ValueError("Number of sheets must be between 1 and 50.")
        if not (3 <= rows <= 25):
            raise ValueError("Grid rows must be between 3 and 25.")
        if not (3 <= cols <= 15):
            raise ValueError("Grid columns must be between 3 and 15.")
        if not (12 <= font_size <= 96):
            raise ValueError("Max word size must be between 12 and 96.")
        return num_sheets, rows, cols, font_size

    def _read_bingo_options(self) -> int:
        """Returns num_cards, validated."""
        try:
            num_cards = int(self.bingo_cards_var.get())
        except (tk.TclError, ValueError):
            raise ValueError("Number of cards must be a whole number.")
        if not (1 <= num_cards <= 30):
            raise ValueError("Number of cards must be between 1 and 30.")
        return num_cards

    def _on_generate_probe_sheets(self) -> None:
        self.status_var.set("")
        try:
            child_name, words, date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
            num_sheets, rows, cols, font_size = self._read_probe_sheet_options()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            sheets = build_probe_sheets(
                child_name=child_name, words=words, num_sheets=num_sheets,
                rows=rows, cols=cols, date_str=date_str,
            )
        except ValueError as exc:
            messagebox.showerror("Couldn't build the sheets", str(exc))
            return

        base_name = _safe_filename(f"{child_name}_probe_sheets")
        try:
            written = self._write_outputs(
                output_dir, base_name, make_pdf, make_docx,
                pdf_fn=lambda path: export_pdf(
                    sheets, path, include_word_list=self.show_word_list_var.get(), grid_font_size=font_size,
                    include_tracker=self.show_tracker_var.get(),
                ),
                docx_fn=lambda path: export_docx(
                    sheets, path, include_word_list=self.show_word_list_var.get(), grid_font_size=font_size,
                    include_tracker=self.show_tracker_var.get(),
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
        self.status_var.set("")
        try:
            child_name, words, date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            sheet = build_pairs_card_sheet(child_name, words, date_str)
        except ValueError as exc:
            messagebox.showerror("Couldn't build the cards", str(exc))
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
        self.status_var.set("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            board = build_board(child_name, words)
        except ValueError as exc:
            messagebox.showerror("Couldn't build the board", str(exc))
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
        self.status_var.set("")
        try:
            child_name, words, date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
            num_cards = self._read_bingo_options()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            cards = build_bingo_cards(child_name, words, date_str, num_cards=num_cards)
        except ValueError as exc:
            messagebox.showerror("Couldn't build the cards", str(exc))
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
        self.status_var.set("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            puzzle = build_word_search(child_name, words)
        except ValueError as exc:
            messagebox.showerror("Couldn't build the puzzle", str(exc))
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
        self.status_var.set("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            trail = build_word_trail(child_name, words)
        except ValueError as exc:
            messagebox.showerror("Couldn't build the trail", str(exc))
            return

        page_size = self.trail_page_size_var.get()
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
    # Large Print Words
    # ------------------------------------------------------------------
    def _on_generate_large_print(self) -> None:
        self.status_var.set("")
        try:
            child_name, words, _date_str = self._collect_child_and_words()
            make_pdf, make_docx, output_dir = self._collect_output_options()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        if not self._ensure_output_dir(output_dir):
            return

        try:
            pages = build_large_print_pages(words)
        except ValueError as exc:
            messagebox.showerror("Couldn't build the pages", str(exc))
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

    # ------------------------------------------------------------------
    # Shared plumbing
    # ------------------------------------------------------------------
    def _ensure_output_dir(self, output_dir: str) -> bool:
        try:
            os.makedirs(output_dir, exist_ok=True)
            return True
        except OSError as exc:
            messagebox.showerror("Can't use that folder", f"Couldn't create the output folder:\n{exc}")
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
        messagebox.showerror(
            "Couldn't save the file",
            f"{exc}\n\nIf the file is already open in another program, close it and try again.",
        )


def _safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "worksheet"


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


def main() -> None:
    root = tk.Tk()
    PrecisionWorksheetApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
