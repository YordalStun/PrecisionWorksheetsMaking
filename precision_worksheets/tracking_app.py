"""The main per-child word-tracking app.

This is the new primary entry point: a home screen listing every child,
an "Add Child" wizard that seeds their starting word list from an initial
checklist, and a per-child screen that generates sheets from whichever 5
words the tracking data says are due, then lets you log a week's results
back in. The original one-off, type-your-own-5-words generator
(precision_worksheets.gui) is still reachable from the home screen for a
quick sheet that doesn't need a tracked child.
"""

from __future__ import annotations

import datetime
import os
import random
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import db
from .data.word_lists import TIERS, TIERS_BY_KEY
from .docx_export import export_docx
from .games.pairs_cards import build_pairs_card_sheet, export_pairs_cards_docx, export_pairs_cards_pdf
from .games.word_trail import build_word_trail, export_word_trail_docx, export_word_trail_pdf
from .generator import build_probe_sheets
from .pdf_export import export_pdf
from .widgets import ScrollableFrame

DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "PrecisionWorksheets")
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
CHECKLIST_COLUMNS = 5


def _safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "child"


_BG = "#f4f6f9"
_PANEL_BG = "#ffffff"
_ACCENT = "#3568b5"
_ACCENT_DARK = "#2a5390"
_TEXT = "#1f2937"
_MUTED = "#6b7280"
_BORDER = "#d7dce3"


def _setup_style(root: tk.Tk) -> None:
    """Applies a light, consistent theme on top of plain ttk widgets."""
    root.configure(background=_BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    default_font = ("Segoe UI", 10)
    header_font = ("Segoe UI", 20, "bold")
    sub_header_font = ("Segoe UI", 13, "bold")

    style.configure(".", background=_BG, foreground=_TEXT, font=default_font)
    style.configure("TFrame", background=_BG)
    style.configure("TLabel", background=_BG, foreground=_TEXT)
    style.configure("Muted.TLabel", background=_BG, foreground=_MUTED)
    style.configure("Header.TLabel", background=_BG, foreground=_TEXT, font=header_font)
    style.configure("SubHeader.TLabel", background=_BG, foreground=_TEXT, font=sub_header_font)
    style.configure("ColHeader.TLabel", background=_BG, foreground=_MUTED, font=("Segoe UI", 10, "bold"))

    style.configure("Card.TFrame", background=_PANEL_BG, relief="flat", borderwidth=1)
    style.configure("Card.TLabel", background=_PANEL_BG, foreground=_TEXT)
    style.configure("CardMuted.TLabel", background=_PANEL_BG, foreground=_MUTED)
    style.configure("Card.TLabelframe", background=_PANEL_BG, foreground=_TEXT, borderwidth=1, relief="solid")
    style.configure("Card.TLabelframe.Label", background=_PANEL_BG, foreground=_TEXT, font=sub_header_font)
    style.configure("Card.TCheckbutton", background=_PANEL_BG, foreground=_TEXT)
    style.configure("Card.TRadiobutton", background=_PANEL_BG, foreground=_TEXT)

    style.configure("TButton", padding=(12, 7), font=default_font, background=_PANEL_BG, foreground=_TEXT)
    style.map("TButton", background=[("active", "#e7ebf1")])

    style.configure(
        "Accent.TButton", padding=(14, 8), font=("Segoe UI", 10, "bold"), background=_ACCENT, foreground="#ffffff"
    )
    style.map("Accent.TButton", background=[("active", _ACCENT_DARK), ("disabled", _BORDER)])

    style.configure("TNotebook", background=_BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 8), font=default_font, background=_BG, foreground=_MUTED)
    style.map(
        "TNotebook.Tab",
        background=[("selected", _PANEL_BG)],
        foreground=[("selected", _TEXT)],
    )

    style.configure("TEntry", padding=6, fieldbackground="#ffffff")
    style.configure("TCheckbutton", background=_BG)
    style.configure("TRadiobutton", background=_BG)
    style.configure("TLabelframe", background=_BG, foreground=_TEXT)
    style.configure("TLabelframe.Label", background=_BG, foreground=_TEXT, font=sub_header_font)
    style.configure("TSeparator", background=_BORDER)

    root.option_add("*TCombobox*Listbox.font", default_font)


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


class TrackingApp:
    """Owns the window and swaps a single content frame between screens,
    so navigating around feels like one app rather than a pile of popups."""

    def __init__(self, root: tk.Tk, db_path: str | None = None):
        self.root = root
        root.title("Precision Worksheet Maker")
        root.geometry("1000x720")
        root.minsize(820, 600)
        _setup_style(root)

        self.conn = db.connect(db_path)

        self.content = ttk.Frame(root, padding=16)
        self.content.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.show_children_list()

    def _clear_content(self) -> None:
        for w in self.content.winfo_children():
            w.destroy()

    def show_children_list(self) -> None:
        self._clear_content()
        ChildrenListScreen(
            self.content, self.conn,
            on_open_child=self.show_child,
            on_add_child=self.show_add_child,
            on_quick_sheet=self.open_quick_sheet,
        )

    def show_add_child(self) -> None:
        self._clear_content()
        AddChildScreen(self.content, self.conn, on_done=self.show_children_list, on_cancel=self.show_children_list)

    def show_child(self, child_id: int) -> None:
        self._clear_content()
        ChildScreen(self.content, self.conn, child_id, on_back=self.show_children_list)

    def open_quick_sheet(self) -> None:
        from .gui import PrecisionWorksheetApp

        top = tk.Toplevel(self.root)
        PrecisionWorksheetApp(top)


class ChildrenListScreen(ttk.Frame):
    def __init__(self, parent: ttk.Frame, conn, on_open_child, on_add_child, on_quick_sheet):
        super().__init__(parent)
        self.grid(row=0, column=0, sticky="nsew")
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Children", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        buttons = ttk.Frame(header)
        buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(buttons, text="+ Add Child", style="Accent.TButton", command=on_add_child).grid(
            row=0, column=0, padx=(0, 8)
        )
        ttk.Button(buttons, text="Quick one-off sheet (no tracking)", command=on_quick_sheet).grid(row=0, column=1)

        children = db.list_children(conn)
        if not children:
            ttk.Label(
                self, text="No children yet - click \"+ Add Child\" to get started.",
                style="Muted.TLabel",
            ).grid(row=1, column=0, sticky="w")
            return

        table = ScrollableFrame(self, height=520)
        table.grid(row=1, column=0, sticky="nsew")
        self.rowconfigure(1, weight=1)

        cols = ttk.Frame(table.inner)
        cols.grid(row=0, column=0, sticky="ew")
        for c, weight in enumerate((2, 1, 2, 1, 0)):
            cols.columnconfigure(c, weight=weight)
        headers = ["Name", "Year group", "Current word list", "Progress", ""]
        for c, text in enumerate(headers):
            ttk.Label(cols, text=text, style="ColHeader.TLabel").grid(
                row=0, column=c, sticky="w", padx=6, pady=(0, 6)
            )

        for r, child in enumerate(children, start=1):
            tier = TIERS_BY_KEY[child["current_tier"]]
            known = len(db.known_words(conn, child["id"], tier.key))
            total = len(tier.words)
            ttk.Label(cols, text=child["name"]).grid(row=r, column=0, sticky="w", padx=6, pady=4)
            ttk.Label(cols, text=child["year_group"] or "").grid(row=r, column=1, sticky="w", padx=6, pady=4)
            ttk.Label(cols, text=tier.label).grid(row=r, column=2, sticky="w", padx=6, pady=4)
            ttk.Label(cols, text=f"{known} / {total} known").grid(row=r, column=3, sticky="w", padx=6, pady=4)
            ttk.Button(
                cols, text="Open", command=lambda cid=child["id"]: on_open_child(cid)
            ).grid(row=r, column=4, sticky="e", padx=6, pady=4)


class AddChildScreen(ttk.Frame):
    def __init__(self, parent: ttk.Frame, conn, on_done, on_cancel):
        super().__init__(parent)
        self.grid(row=0, column=0, sticky="nsew")
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.conn = conn
        self.on_done = on_done
        self.checklist_vars: dict[str, tk.BooleanVar] = {}

        ttk.Label(self, text="Add a Child", style="Header.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 16)
        )

        form = ttk.Frame(self)
        form.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(form, text="Child's name:").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.name_var, width=24).grid(row=0, column=1, sticky="w", padx=(6, 24))

        ttk.Label(form, text="Year group:").grid(row=0, column=2, sticky="w")
        self.year_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.year_var, width=14).grid(row=0, column=3, sticky="w", padx=(6, 0))

        ttk.Label(form, text="Which word list are they currently on?").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(12, 4)
        )
        self.tier_var = tk.StringVar(value=TIERS[0].key)
        tier_buttons = ttk.Frame(form)
        tier_buttons.grid(row=2, column=0, columnspan=4, sticky="w")
        for i, tier in enumerate(TIERS):
            ttk.Radiobutton(
                tier_buttons, text=tier.label, value=tier.key, variable=self.tier_var, command=self._rebuild_checklist,
            ).grid(row=0, column=i, sticky="w", padx=(0, 16))

        ttk.Label(
            self,
            text="Tick every word they already know from that list - everything left unticked\n"
            "is what the app will start introducing, in list order.",
            justify="left", style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="nw", pady=(0, 6))

        self.checklist_holder = ttk.Frame(self)
        self.checklist_holder.grid(row=3, column=0, sticky="nsew")
        self.rowconfigure(3, weight=1)
        self.columnconfigure(0, weight=1)

        buttons = ttk.Frame(self)
        buttons.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=on_cancel).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Add child", style="Accent.TButton", command=self._submit).grid(row=0, column=1)

        self._rebuild_checklist()

    def _rebuild_checklist(self) -> None:
        for w in self.checklist_holder.winfo_children():
            w.destroy()
        self.checklist_vars = {}

        tier = TIERS_BY_KEY[self.tier_var.get()]
        scroll = ScrollableFrame(self.checklist_holder, height=360)
        scroll.pack(fill="both", expand=True)

        for i, word in enumerate(tier.words):
            var = tk.BooleanVar(value=False)
            self.checklist_vars[word] = var
            row, col = divmod(i, CHECKLIST_COLUMNS)
            ttk.Checkbutton(scroll.inner, text=word, variable=var).grid(
                row=row, column=col, sticky="w", padx=8, pady=2
            )

    def _submit(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Check your details", "Please enter the child's name.")
            return
        known = {word for word, var in self.checklist_vars.items() if var.get()}
        try:
            db.add_child(self.conn, name, self.year_var.get(), self.tier_var.get(), known)
        except ValueError as exc:
            messagebox.showerror("Couldn't add child", str(exc))
            return
        self.on_done()


class ChildScreen(ttk.Frame):
    def __init__(self, parent: ttk.Frame, conn, child_id: int, on_back):
        super().__init__(parent)
        self.grid(row=0, column=0, sticky="nsew")
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.conn = conn
        self.child_id = child_id
        self.on_back = on_back
        self.output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        self.current_words: list[str] = []

        self._build()

    def _child(self):
        return db.get_child(self.conn, self.child_id)

    def _build(self) -> None:
        for w in self.winfo_children():
            w.destroy()

        child = self._child()
        if child is None:
            ttk.Label(self, text="This child no longer exists.").grid(row=0, column=0, sticky="w")
            ttk.Button(self, text="Back to children", command=self.on_back).grid(row=1, column=0, sticky="w", pady=8)
            return

        tier = TIERS_BY_KEY[child["current_tier"]]
        known = len(db.known_words(self.conn, self.child_id, tier.key))
        total = len(tier.words)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(1, weight=1)
        ttk.Button(header, text="← Back", command=self.on_back).grid(row=0, column=0, sticky="w")
        title = ttk.Frame(header)
        title.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(title, text=child["name"], style="Header.TLabel").grid(row=0, column=0, sticky="w")
        subtitle = f"{child['year_group'] or 'No year group set'}  ·  {tier.label}  ·  {known} / {total} known"
        ttk.Label(title, text=subtitle, style="Muted.TLabel").grid(row=1, column=0, sticky="w")

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew")
        self.rowconfigure(1, weight=1)
        notebook.add(self._build_sheets_tab(notebook), text="This Week's Sheets")
        notebook.add(self._build_history_tab(notebook), text="History")

    # ------------------------------------------------------------------
    # Sheets tab
    # ------------------------------------------------------------------
    def _build_sheets_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)
        tab.columnconfigure(0, weight=1)

        self.current_words = db.choose_session_words(self.conn, self.child_id, rng=random.Random())

        words_box = ttk.LabelFrame(tab, text="Next sheet will use", padding=12)
        words_box.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.words_label_var = tk.StringVar()
        self._refresh_words_label()
        ttk.Label(words_box, textvariable=self.words_label_var, font=("TkDefaultFont", 13)).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            words_box,
            text="The 3 practice words are picked automatically (struggling words first, then\n"
            "the next new ones) - only the 2 known words are random, so you can reshuffle those.",
            foreground="#666666", justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(words_box, text="\U0001f500 Shuffle known words", command=self._shuffle_known).grid(
            row=2, column=0, sticky="w", pady=(8, 0)
        )

        output_box = ttk.LabelFrame(tab, text="Save to", padding=12)
        output_box.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        output_box.columnconfigure(0, weight=1)
        ttk.Entry(output_box, textvariable=self.output_dir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_box, text="Browse...", command=self._browse_output_dir).grid(row=0, column=1, padx=(8, 0))

        ttk.Button(
            tab, text="Generate sheets (probe sheet, word trail, matching pairs)",
            style="Accent.TButton", command=self._generate_sheets,
        ).grid(row=2, column=0, sticky="w", pady=(0, 16))

        ttk.Separator(tab).grid(row=3, column=0, sticky="ew", pady=(0, 16))

        ttk.Button(
            tab, text="Record this week's results →", style="Accent.TButton", command=self._open_record_dialog,
        ).grid(row=4, column=0, sticky="w")

        self.status_var = tk.StringVar(value="")
        ttk.Label(tab, textvariable=self.status_var, foreground="#2a6b2a").grid(row=5, column=0, sticky="w", pady=(12, 0))

        return tab

    def _refresh_words_label(self) -> None:
        practice, known = self.current_words[:3], self.current_words[3:]
        self.words_label_var.set("Practising: " + ", ".join(practice) + "   ·   Known: " + ", ".join(known))

    def _shuffle_known(self) -> None:
        tier_key = self._child()["current_tier"]
        known_pool = db.all_known_words(self.conn, self.child_id, tier_key)
        from .tracking import pick_known_words

        self.current_words = self.current_words[:3] + pick_known_words(known_pool, random.Random())
        self._refresh_words_label()

    def _browse_output_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_dir_var.get() or os.getcwd())
        if chosen:
            self.output_dir_var.set(chosen)

    def _generate_sheets(self) -> None:
        child = self._child()
        output_dir = os.path.join(self.output_dir_var.get().strip() or DEFAULT_OUTPUT_DIR, _safe_filename(child["name"]))
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Can't use that folder", f"Couldn't create the output folder:\n{exc}")
            return

        words = list(self.current_words)
        date_str = datetime.date.today().strftime("%d/%m/%Y")
        base = _safe_filename(child["name"])

        try:
            sheets = build_probe_sheets(child_name=child["name"], words=words, num_sheets=1, rows=4, cols=5, date_str=date_str)
            export_pdf(sheets, os.path.join(output_dir, f"{base}_probe_sheet.pdf"))
            export_docx(sheets, os.path.join(output_dir, f"{base}_probe_sheet.docx"))

            trail = build_word_trail(child["name"], words)
            export_word_trail_pdf(trail, os.path.join(output_dir, f"{base}_word_trail.pdf"), page_size="A4")
            export_word_trail_docx(trail, os.path.join(output_dir, f"{base}_word_trail.docx"), page_size="A4")

            pairs = build_pairs_card_sheet(child["name"], words, date_str)
            export_pairs_cards_pdf(pairs, os.path.join(output_dir, f"{base}_matching_pairs.pdf"))
            export_pairs_cards_docx(pairs, os.path.join(output_dir, f"{base}_matching_pairs.docx"))
        except (ValueError, OSError) as exc:
            messagebox.showerror("Couldn't generate the sheets", str(exc))
            return

        db.set_last_sheet(self.conn, self.child_id, words, date_str)
        self.status_var.set(f"Done! 6 files saved in {output_dir}")
        if messagebox.askyesno("Sheets created", "Sheets created. Open the folder now?"):
            _open_folder(output_dir)

    # ------------------------------------------------------------------
    # Record results
    # ------------------------------------------------------------------
    def _open_record_dialog(self) -> None:
        words = db.get_last_sheet_words(self.conn, self.child_id) or self.current_words
        RecordResultsDialog(self, self.conn, self.child_id, words, on_saved=self._on_recorded)

    def _on_recorded(self) -> None:
        self._build()

    # ------------------------------------------------------------------
    # History tab
    # ------------------------------------------------------------------
    def _build_history_tab(self, notebook: ttk.Notebook) -> ttk.Frame:
        tab = ttk.Frame(notebook, padding=12)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        sessions = db.get_sessions(self.conn, self.child_id)
        if not sessions:
            ttk.Label(tab, text="No results recorded yet.", foreground="#666666").grid(row=0, column=0, sticky="w")
            return tab

        scroll = ScrollableFrame(tab, height=540)
        scroll.grid(row=0, column=0, sticky="nsew")

        for r, session in enumerate(sessions):
            row = ttk.LabelFrame(scroll.inner, text=session["date"], padding=8)
            row.grid(row=r, column=0, sticky="ew", padx=4, pady=4)
            scroll.inner.columnconfigure(0, weight=1)

            bits = []
            if session["time_seconds"] is not None:
                bits.append(f"{session['time_seconds']}s")
            if session["correct_count"] is not None:
                bits.append(f"{session['correct_count']} correct")
            if session["error_count"] is not None:
                bits.append(f"{session['error_count']} errors")
            if bits:
                ttk.Label(row, text="  ·  ".join(bits), style="Muted.TLabel").grid(row=0, column=0, sticky="w")

            words_row = ttk.Frame(row)
            words_row.grid(row=1, column=0, sticky="w", pady=(4, 0))
            for c, wr in enumerate(db.get_session_words(self.conn, session["id"])):
                mark = "✓" if wr["correct"] else "✗"
                color = "#2a6b2a" if wr["correct"] else "#a03030"
                ttk.Label(words_row, text=f"{wr['word']} {mark}", foreground=color).grid(
                    row=0, column=c, padx=(0, 12)
                )

            if session["notes"]:
                ttk.Label(row, text=session["notes"], foreground="#444444", wraplength=700, justify="left").grid(
                    row=2, column=0, sticky="w", pady=(4, 0)
                )

        return tab


class RecordResultsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, conn, child_id: int, words: list[str], on_saved):
        super().__init__(parent)
        self.title("Record this week's results")
        self.resizable(False, False)
        self.conn = conn
        self.child_id = child_id
        self.words = words
        self.on_saved = on_saved
        self.grab_set()

        outer = ttk.Frame(self, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")

        ttk.Label(outer, text="Date:").grid(row=0, column=0, sticky="w")
        self.date_var = tk.StringVar(value=datetime.date.today().strftime("%d/%m/%Y"))
        ttk.Entry(outer, textvariable=self.date_var, width=14).grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(outer, text="Tick each word they got right this time:").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(12, 4)
        )
        self.word_vars: dict[str, tk.BooleanVar] = {}
        for i, word in enumerate(words):
            var = tk.BooleanVar(value=True)
            self.word_vars[word] = var
            ttk.Checkbutton(outer, text=word, variable=var).grid(row=2 + i, column=0, columnspan=2, sticky="w")

        next_row = 2 + len(words)
        ttk.Label(outer, text="Time (seconds):").grid(row=next_row, column=0, sticky="w", pady=(12, 0))
        self.time_var = tk.StringVar()
        ttk.Entry(outer, textvariable=self.time_var, width=8).grid(row=next_row, column=1, sticky="w", padx=(6, 0), pady=(12, 0))

        ttk.Label(outer, text="Correct (overall):").grid(row=next_row + 1, column=0, sticky="w")
        self.correct_var = tk.StringVar()
        ttk.Entry(outer, textvariable=self.correct_var, width=8).grid(row=next_row + 1, column=1, sticky="w", padx=(6, 0))

        ttk.Label(outer, text="Errors (overall):").grid(row=next_row + 2, column=0, sticky="w")
        self.errors_var = tk.StringVar()
        ttk.Entry(outer, textvariable=self.errors_var, width=8).grid(row=next_row + 2, column=1, sticky="w", padx=(6, 0))

        ttk.Label(outer, text="Notes:").grid(row=next_row + 3, column=0, sticky="nw", pady=(8, 0))
        self.notes_text = tk.Text(outer, width=32, height=3)
        self.notes_text.grid(row=next_row + 3, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.grid(row=next_row + 4, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Save", style="Accent.TButton", command=self._submit).grid(row=0, column=1)

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
            time_seconds = self._parse_optional_int(self.time_var.get(), "Time")
            correct_count = self._parse_optional_int(self.correct_var.get(), "Correct")
            error_count = self._parse_optional_int(self.errors_var.get(), "Errors")
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        date_str = self.date_var.get().strip() or datetime.date.today().strftime("%d/%m/%Y")
        word_results = [(word, var.get()) for word, var in self.word_vars.items()]
        notes = self.notes_text.get("1.0", "end").strip()

        before_tier = db.get_child(self.conn, self.child_id)["current_tier"]
        db.record_session(
            self.conn, self.child_id, date_str, word_results,
            time_seconds=time_seconds, correct_count=correct_count, error_count=error_count, notes=notes,
        )
        after = db.get_child(self.conn, self.child_id)

        self.destroy()
        self.on_saved()
        if after["current_tier"] != before_tier:
            new_tier = TIERS_BY_KEY[after["current_tier"]]
            messagebox.showinfo(
                "Word list complete!",
                f"{after['name']} has learned every word on their current list and has "
                f"moved on to {new_tier.label}.",
            )


def main() -> None:
    root = tk.Tk()
    TrackingApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
