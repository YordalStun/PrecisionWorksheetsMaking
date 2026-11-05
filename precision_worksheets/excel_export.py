"""Exports a child's full tracking record to a nicely formatted .xlsx
workbook: an overview, their current word list with mastery state, and
their full session history (both a summary row per week and the
per-word right/wrong detail behind it)."""

from __future__ import annotations

import sqlite3

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from . import db
from .data.word_lists import TIERS_BY_KEY
from .tracking import STATUS_KNOWN

ACCENT = "3568B5"
ACCENT_DARK = "2A5390"
HEADER_FILL = PatternFill("solid", fgColor=ACCENT)
HEADER_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(size=16, bold=True, color="1F2937")
SUBTITLE_FONT = Font(size=10, color="6B7280")
LABEL_FONT = Font(bold=True, color="1F2937")
KNOWN_FILL = PatternFill("solid", fgColor="E3F0E3")
LEARNING_FILL = PatternFill("solid", fgColor="FBEFE0")
CORRECT_FONT = Font(color="2A6B2A")
WRONG_FONT = Font(color="A03030")
THIN_BORDER = Border(bottom=Side(style="thin", color="D7DCE3"))


def _style_header_row(ws: Worksheet, row: int, num_cols: int) -> None:
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center")


def _autofit(ws: Worksheet, widths: list[int]) -> None:
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width


def export_child_report(conn: sqlite3.Connection, child_id: int, path: str) -> None:
    child = db.get_child(conn, child_id)
    if child is None:
        raise ValueError("This child no longer exists.")

    wb = Workbook()
    _build_overview_sheet(wb.active, conn, child)
    _build_word_list_sheet(wb.create_sheet("Current Word List"), conn, child)
    sessions = db.get_sessions(conn, child_id)
    _build_history_sheet(wb.create_sheet("Session History"), sessions)
    _build_word_detail_sheet(wb.create_sheet("Session Word Detail"), conn, sessions)

    wb.save(path)


def _build_overview_sheet(ws: Worksheet, conn: sqlite3.Connection, child: sqlite3.Row) -> None:
    ws.title = "Overview"
    tier = TIERS_BY_KEY[child["current_tier"]]
    known = len(db.known_words(conn, child["id"], tier.key))
    total = len(tier.words)
    sessions = db.get_sessions(conn, child["id"])

    ws["A1"] = child["name"]
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Year group: {child['year_group'] or 'Not set'}"
    ws["A2"].font = SUBTITLE_FONT

    rows = [
        ("Current word list", tier.label),
        ("Words known", f"{known} / {total}"),
        ("Started tracking on", child["created_at"][:10]),
        ("Last sheet generated", child["last_sheet_date"] or "Never"),
        ("Weeks of results recorded", str(len(sessions))),
    ]
    r = 4
    for label, value in rows:
        ws.cell(row=r, column=1, value=label).font = LABEL_FONT
        ws.cell(row=r, column=2, value=value)
        r += 1

    _autofit(ws, [26, 36])


def _build_word_list_sheet(ws: Worksheet, conn: sqlite3.Connection, child: sqlite3.Row) -> None:
    tier = TIERS_BY_KEY[child["current_tier"]]
    headers = ["Word", "Status", "Correct streak", "Times seen", "Times correct"]
    for col, text in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=text)
    _style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "A2"

    states = {s.word: s for s in db.get_word_states(conn, child["id"], tier.key)}
    for r, word in enumerate(tier.words, start=2):
        state = states.get(word)
        status = state.status if state else "learning"
        ws.cell(row=r, column=1, value=word)
        ws.cell(row=r, column=2, value=status.title())
        ws.cell(row=r, column=3, value=state.correct_streak if state else 0)
        ws.cell(row=r, column=4, value=state.times_seen if state else 0)
        ws.cell(row=r, column=5, value=state.times_correct if state else 0)

        fill = KNOWN_FILL if status == STATUS_KNOWN else LEARNING_FILL
        for col in range(1, len(headers) + 1):
            ws.cell(row=r, column=col).fill = fill

    _autofit(ws, [18, 14, 14, 12, 14])


def _build_history_sheet(ws: Worksheet, sessions: list[sqlite3.Row]) -> None:
    headers = ["Date", "Time (seconds)", "Correct (overall)", "Errors (overall)", "Notes"]
    for col, text in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=text)
    _style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "A2"

    if not sessions:
        ws.cell(row=2, column=1, value="No results recorded yet.")
        _autofit(ws, [14, 16, 16, 16, 50])
        return

    for r, session in enumerate(sessions, start=2):
        ws.cell(row=r, column=1, value=session["date"])
        ws.cell(row=r, column=2, value=session["time_seconds"])
        ws.cell(row=r, column=3, value=session["correct_count"])
        ws.cell(row=r, column=4, value=session["error_count"])
        ws.cell(row=r, column=5, value=session["notes"] or "")
        for col in range(1, len(headers) + 1):
            ws.cell(row=r, column=col).border = THIN_BORDER

    _autofit(ws, [14, 16, 16, 16, 50])


def _build_word_detail_sheet(ws: Worksheet, conn: sqlite3.Connection, sessions: list[sqlite3.Row]) -> None:
    headers = ["Date", "Word", "Result"]
    for col, text in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=text)
    _style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "A2"

    r = 2
    for session in sessions:
        for wr in db.get_session_words(conn, session["id"]):
            ws.cell(row=r, column=1, value=session["date"])
            ws.cell(row=r, column=2, value=wr["word"])
            result_cell = ws.cell(row=r, column=3, value="Correct" if wr["correct"] else "Wrong")
            result_cell.font = CORRECT_FONT if wr["correct"] else WRONG_FONT
            r += 1

    if r == 2:
        ws.cell(row=2, column=1, value="No results recorded yet.")

    _autofit(ws, [14, 18, 12])
