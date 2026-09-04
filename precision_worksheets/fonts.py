"""Locate a comic/handwriting-style font to use in generated files.

We deliberately never bundle Microsoft's Comic Sans MS itself - it's a
proprietary font and redistributing the file would break its licence.
Instead, at run time we look for the real font file already installed on
the machine. On Windows that's virtually guaranteed: Comic Sans MS has
shipped with every edition of Windows since 3.1, normally at
C:\\Windows\\Fonts\\comic.ttf (comicbd.ttf for bold).

Two different consumers need this:
  - reportlab (PDF text) needs a font *registered* under a name, and only
    accepts TrueType (glyf-outline) files.
  - Pillow (the Snakes & Ladders board image) needs a font *file path*, and
    can render OpenType/CFF files too.

If the real Comic Sans MS can't be found - e.g. running somewhere other
than Windows for development - reportlab falls back to a plain built-in
PDF font, while Pillow falls back to a bundled copy of Comic Neue (SIL
Open Font License - see assets/fonts/OFL.txt), a free font designed as a
Comic Sans lookalike, so the board still gets a comic-style look.
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

_ASSETS_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
_BUNDLED_REGULAR = os.path.join(_ASSETS_FONT_DIR, "ComicNeue-Regular.otf")
_BUNDLED_BOLD = os.path.join(_ASSETS_FONT_DIR, "ComicNeue-Bold.otf")

_cached_pdf_names: tuple[str, str] | None = None
_cached_board_paths: tuple[str, str] | None = None


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


def find_windows_comic_sans_files() -> tuple[str | None, str | None]:
    """Look for the real Comic Sans MS files on this machine.

    Returns (regular_path, bold_path); either may be None if not found.
    """
    dirs = _candidate_font_dirs()
    regular_path = _find_font_file(dirs, _REGULAR_FILENAMES)
    bold_path = _find_font_file(dirs, _BOLD_FILENAMES) if regular_path else None
    return regular_path, bold_path


def get_comic_font_names() -> tuple[str, str]:
    """Return (regular_font_name, bold_font_name) already registered with
    reportlab's pdfmetrics, ready to use in a FONTNAME table/paragraph style.

    Looks for the real Comic Sans MS the first time it's called and
    registers it if found; the result is cached for the rest of the process.
    Falls back to reportlab's built-in Helvetica if the font can't be found
    (reportlab can only embed TrueType outlines, so the bundled Comic Neue
    - an OpenType/CFF font - isn't usable here; see get_board_font_paths).
    """
    global _cached_pdf_names
    if _cached_pdf_names is not None:
        return _cached_pdf_names

    regular_path, bold_path = find_windows_comic_sans_files()
    if regular_path:
        try:
            pdfmetrics.registerFont(TTFont(REGULAR_FONT_NAME, regular_path))
            pdfmetrics.registerFont(TTFont(BOLD_FONT_NAME, bold_path or regular_path))
            _cached_pdf_names = (REGULAR_FONT_NAME, BOLD_FONT_NAME)
            return _cached_pdf_names
        except Exception:
            pass  # Corrupt or unreadable font file - fall through below.

    _cached_pdf_names = (_FALLBACK_REGULAR, _FALLBACK_BOLD)
    return _cached_pdf_names


def get_board_font_paths() -> tuple[str, str]:
    """Return (regular_path, bold_path) for Pillow to load with
    ImageFont.truetype(). Always returns real files: the genuine Comic Sans
    MS if this machine has it, otherwise the bundled Comic Neue fallback.
    """
    global _cached_board_paths
    if _cached_board_paths is not None:
        return _cached_board_paths

    regular_path, bold_path = find_windows_comic_sans_files()
    _cached_board_paths = (regular_path or _BUNDLED_REGULAR, bold_path or regular_path or _BUNDLED_BOLD)
    return _cached_board_paths
