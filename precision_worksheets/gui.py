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
from .generator import build_probe_sheets
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
        self.make_pdf_var = tk.BooleanVar(value=True)
        self.make_docx_var = tk.BooleanVar(value=True)
        self.output_dir_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        self.status_var = tk.StringVar(value="")

        outer = ttk.Frame(root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")

        self._build_child_section(outer, row=0)
        self._build_options_section(outer, row=1)
        self._build_output_section(outer, row=2)
        self._build_actions_section(outer, row=3)

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

    def _build_options_section(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Sheet options", padding=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(frame, text="Number of sheets to print:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(frame, from_=1, to=50, textvariable=self.sheets_var, width=6).grid(
            row=0, column=1, sticky="w", padx=(6, 24)
        )

        ttk.Label(frame, text="Grid rows:").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(frame, from_=3, to=25, textvariable=self.rows_var, width=6).grid(
            row=0, column=3, sticky="w", padx=(6, 24)
        )

        ttk.Label(frame, text="Grid columns:").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(frame, from_=3, to=15, textvariable=self.cols_var, width=6).grid(
            row=0, column=5, sticky="w", padx=(6, 0)
        )

        ttk.Label(frame, text="Max word size:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(frame, from_=12, to=96, textvariable=self.font_size_var, width=6).grid(
            row=1, column=1, sticky="w", padx=(6, 24), pady=(8, 0)
        )

        ttk.Checkbutton(
            frame,
            text="Show the word list at the top of each sheet",
            variable=self.show_word_list_var,
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(10, 0))

        formats = ttk.Frame(frame)
        formats.grid(row=3, column=0, columnspan=6, sticky="w", pady=(10, 0))
        ttk.Label(formats, text="Create:").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(formats, text="PDF", variable=self.make_pdf_var).grid(
            row=0, column=1, sticky="w", padx=(10, 10)
        )
        ttk.Checkbutton(formats, text="Word document (.docx)", variable=self.make_docx_var).grid(
            row=0, column=2, sticky="w"
        )

    def _build_output_section(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.LabelFrame(parent, text="Save to", padding=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))

        ttk.Entry(frame, textvariable=self.output_dir_var, width=48).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(frame, text="Browse...", command=self._browse_output_dir).grid(
            row=0, column=1, padx=(8, 0)
        )

    def _build_actions_section(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew")

        ttk.Button(frame, text="Generate worksheets", command=self._on_generate).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(frame, textvariable=self.status_var, foreground="#2a6b2a").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _browse_output_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_dir_var.get() or os.getcwd())
        if chosen:
            self.output_dir_var.set(chosen)

    def _on_generate(self) -> None:
        self.status_var.set("")
        try:
            params = self._collect_and_validate()
        except ValueError as exc:
            messagebox.showerror("Check your details", str(exc))
            return

        try:
            os.makedirs(params["output_dir"], exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Can't use that folder", f"Couldn't create the output folder:\n{exc}")
            return

        try:
            sheets = build_probe_sheets(
                child_name=params["child_name"],
                words=params["words"],
                num_sheets=params["num_sheets"],
                rows=params["rows"],
                cols=params["cols"],
                date_str=params["date_str"],
            )
        except ValueError as exc:
            messagebox.showerror("Couldn't build the sheets", str(exc))
            return

        base_name = _safe_filename(f"{params['child_name']}_probe_sheets")
        written = []
        try:
            if params["make_pdf"]:
                pdf_path = os.path.join(params["output_dir"], base_name + ".pdf")
                export_pdf(
                    sheets, pdf_path,
                    include_word_list=params["show_word_list"],
                    grid_font_size=params["font_size"],
                )
                written.append(pdf_path)
            if params["make_docx"]:
                docx_path = os.path.join(params["output_dir"], base_name + ".docx")
                export_docx(
                    sheets, docx_path,
                    include_word_list=params["show_word_list"],
                    grid_font_size=params["font_size"],
                )
                written.append(docx_path)
        except OSError as exc:
            messagebox.showerror(
                "Couldn't save the file",
                f"{exc}\n\nIf the file is already open in another program, close it and try again.",
            )
            return

        self.status_var.set(f"Done! Created {len(written)} file(s) in {params['output_dir']}")
        if messagebox.askyesno(
            "Worksheets created",
            f"Created {len(written)} file(s):\n" + "\n".join(os.path.basename(p) for p in written)
            + f"\n\nOpen the folder now?",
        ):
            _open_folder(params["output_dir"])

    def _collect_and_validate(self) -> dict:
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

        try:
            num_sheets = int(self.sheets_var.get())
            rows = int(self.rows_var.get())
            cols = int(self.cols_var.get())
            font_size = int(self.font_size_var.get())
        except (tk.TclError, ValueError):
            raise ValueError("Sheets, rows, columns and font size must be whole numbers.")

        if not (1 <= num_sheets <= 50):
            raise ValueError("Number of sheets must be between 1 and 50.")
        if not (3 <= rows <= 25):
            raise ValueError("Grid rows must be between 3 and 25.")
        if not (3 <= cols <= 15):
            raise ValueError("Grid columns must be between 3 and 15.")
        if not (12 <= font_size <= 96):
            raise ValueError("Max word size must be between 12 and 96.")

        make_pdf = self.make_pdf_var.get()
        make_docx = self.make_docx_var.get()
        if not (make_pdf or make_docx):
            raise ValueError("Please tick at least one output format (PDF or Word).")

        output_dir = self.output_dir_var.get().strip() or DEFAULT_OUTPUT_DIR

        return {
            "child_name": child_name,
            "words": words,
            "date_str": date_str,
            "num_sheets": num_sheets,
            "rows": rows,
            "cols": cols,
            "font_size": font_size,
            "show_word_list": self.show_word_list_var.get(),
            "make_pdf": make_pdf,
            "make_docx": make_docx,
            "output_dir": output_dir,
        }


def _safe_filename(name: str) -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("_", name).strip().strip(".")
    return cleaned or "probe_sheets"


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
