"""Locate a comic/handwriting-style TrueType font to use in generated PDFs.

We deliberately never bundle Microsoft's Comic Sans MS itself - it's a
proprietary font and redistributing the file would break its licence.
Instead, at run time we look for the real font file already installed on
the machine. On Windows that's virtually guaranteed: Comic Sans MS has
shipped with every edition of Windows since 3.1, normally at
C:\\Windows\\Fonts\\comic.ttf (comicbd.ttf for bold). If it can't be found
- e.g. this is being run somewhere other than Windows for development - we
fall back to a plain built-in PDF font so the app still works, just
without the comic styling.
"""

from __future__ import annotations

import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

REGULAR_FONT_NAME = "ComicSansMS"
BOLD_FONT_NAME = "ComicSansMS-Bold"

_FALLBACK_REGULAR = "Helvetica"
_FALLBACK_BOLD = "Helvetica-Bold"

_REGULAR_FILENAMES = ["comic.ttf", "Comic.ttf", "COMIC.TTF"]
_BOLD_FILENAMES = ["comicbd.ttf", "Comicbd.ttf", "COMICBD.TTF"]

_cached_names: tuple[str, str] | None = None


def _candidate_font_dirs() -> list[str]:
    dirs = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        dirs.append(os.path.join(windir, "Fonts"))
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        # Fonts installed "for me only" on newer Windows versions.
        dirs.append(os.path.join(local_appdata, "Microsoft", "Windows", "Fonts"))
    dirs.append(r"C:\Windows\Fonts")
    return dirs


def _find_font_file(dirs: list[str], filenames: list[str]) -> str | None:
    for directory in dirs:
        for filename in filenames:
            path = os.path.join(directory, filename)
            if os.path.isfile(path):
                return path
    return None


def get_comic_font_names() -> tuple[str, str]:
    """Return (regular_font_name, bold_font_name) already registered with
    reportlab's pdfmetrics, ready to use in a FONTNAME table/paragraph style.

    Looks for the real Comic Sans MS the first time it's called and
    registers it if found; the result is cached for the rest of the process.
    Falls back to reportlab's built-in Helvetica if the font can't be found.
    """
    global _cached_names
    if _cached_names is not None:
        return _cached_names

    dirs = _candidate_font_dirs()
    regular_path = _find_font_file(dirs, _REGULAR_FILENAMES)

    if regular_path:
        bold_path = _find_font_file(dirs, _BOLD_FILENAMES) or regular_path
        try:
            pdfmetrics.registerFont(TTFont(REGULAR_FONT_NAME, regular_path))
            pdfmetrics.registerFont(TTFont(BOLD_FONT_NAME, bold_path))
            _cached_names = (REGULAR_FONT_NAME, BOLD_FONT_NAME)
            return _cached_names
        except Exception:
            pass  # Corrupt or unreadable font file - fall through below.

    _cached_names = (_FALLBACK_REGULAR, _FALLBACK_BOLD)
    return _cached_names
