"""Shared colour palette and Qt stylesheet for a modern, native-feeling
Windows look (flat, rounded, light theme) across every screen."""

from __future__ import annotations

BG = "#f3f5f9"
PANEL_BG = "#ffffff"
ACCENT = "#3568b5"
ACCENT_DARK = "#2a5390"
ACCENT_LIGHT = "#e8eefb"
TEXT = "#1f2937"
MUTED = "#6b7280"
BORDER = "#d7dce3"
DANGER = "#c0392b"

STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}

QWidget {{
    background: {BG};
}}

QMainWindow, #ContentHost {{
    background: {BG};
}}

QLabel#HeaderLabel {{
    font-size: 20pt;
    font-weight: 600;
}}

QLabel#SubHeaderLabel {{
    font-size: 11pt;
    font-weight: 600;
}}

QLabel#MutedLabel {{
    color: {MUTED};
}}

QFrame#Card {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QGroupBox {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT};
}}

QPushButton {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{
    background: #eef1f6;
}}
QPushButton:pressed {{
    background: #e2e6ed;
}}
QPushButton:disabled {{
    color: {MUTED};
    background: #eceef2;
}}

QPushButton#AccentButton {{
    background: {ACCENT};
    border: 1px solid {ACCENT_DARK};
    color: white;
    font-weight: 600;
    padding: 9px 16px;
}}
QPushButton#AccentButton:hover {{
    background: {ACCENT_DARK};
}}
QPushButton#AccentButton:pressed {{
    background: #1f3f6e;
}}
QPushButton#AccentButton:disabled {{
    background: {BORDER};
    border: 1px solid {BORDER};
    color: #9aa2ad;
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}

QCheckBox, QRadioButton {{
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid #9aa2ad;
    background: white;
}}
QCheckBox::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1.5px solid {ACCENT};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {ACCENT};
    border: 1.5px solid {ACCENT_DARK};
}}

QTableWidget {{
    background: {PANEL_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER};
    alternate-background-color: #f8f9fb;
}}
QHeaderView::section {{
    background: {PANEL_BG};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 6px;
    font-weight: 600;
}}
QTableWidget::item {{
    padding: 4px;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {PANEL_BG};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 9px 18px;
    margin-right: 2px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{
    background: {PANEL_BG};
    color: {TEXT};
    font-weight: 600;
    border: 1px solid {BORDER};
    border-bottom: none;
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
}}

QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c6cbd3;
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #aab0ba;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QProgressBar {{
    background: #eceef2;
    border: none;
    border-radius: 6px;
    height: 10px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 6px;
}}

QToolTip {{
    background: {TEXT};
    color: white;
    border: none;
    padding: 4px 8px;
    border-radius: 4px;
}}
"""
