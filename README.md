# Precision Worksheet Maker

A small local desktop app for creating **Precision Teaching probe sheets** -
the "see it, say it" fluency practice grids where a child reads through a
page of repeated, shuffled sight words as fast and accurately as they can.
Inspired by the layout of [Worksheet Genius's Precision Teaching
generator](https://worksheetgenius.com/design/precision-worksheet/).

You type in a child's first name and 5 words, choose how many sheets you
want, and it creates a printable **PDF** and/or **Word (.docx)** file with
one probe sheet per page - ready to print off in bulk.

## What a probe sheet looks like

Each page has:

- A header with the child's name, the date, and the sheet number
- (Optional) the list of the 5 target words for reference
- A grid of cells (5 columns x 4 rows by default, adjustable) filled with
  the 5 words, repeated evenly and shuffled so no two neighbouring cells
  hold the same word (stops the child from just reading down a line of the
  same word) - each sheet in a batch is shuffled differently, so re-using
  the pack doesn't let a child memorise the order
- Row numbers down the left edge, so you can count how far the child got
- Everything is set in **Comic Sans MS** (see the Fonts section below) for
  a friendly, easy-to-read look
- A scoring line at the bottom: time taken, number correct, number of
  errors, and correct-per-minute, ready to fill in by hand while listening
  to the child read

## Requirements

- Windows 10/11
- [Python 3.10+](https://python.org) if running from source or building
  the `.exe` yourself (tick **"Add python.exe to PATH"** during install).
  Not needed once you have a built `.exe`.

## Quick start (run from source)

```
pip install -r requirements.txt
python run.py
```

This opens the app window. Tkinter (the GUI toolkit used here) ships with
the standard Windows Python installer, so no extra GUI packages are needed.

## Building a standalone Windows .exe

Cross-building a Windows executable isn't possible from this Linux
sandbox, so this step needs to be run once **on your own Windows PC**:

1. Copy this project folder onto your Windows machine (or `git clone` it).
2. Double-click `build_windows_exe.bat`.
3. It installs the required packages plus [PyInstaller](https://pyinstaller.org)
   and builds `dist\PrecisionWorksheetMaker.exe`.
4. Copy that `.exe` anywhere you like (e.g. the Desktop) - it runs without
   Python installed from then on.

## How to use it

1. Open the app.
2. Enter the child's first name.
3. Enter the 5 words you want them to practise.
4. (Optional) adjust the number of sheets to print, the grid size, font
   size, whether the word list is shown at the top of each sheet, and
   which file format(s) to create.
5. Choose (or accept the default) output folder - it defaults to
   `Documents\PrecisionWorksheets`.
6. Click **Generate worksheets**. The PDF/Word file appears in that folder,
   containing one probe sheet per page, ready to print in bulk.

## Fonts

Every sheet is set in **Comic Sans MS**. It's a standard Windows font (has
shipped with every edition of Windows since 3.1), so:

- **Word (.docx) files** just reference it by name - Word uses whatever
  copy is already installed on the PC that opens the file, which on
  Windows is always the real thing.
- **PDF files** need the actual font file embedded at the point the PDF is
  built (that's how PDF works). The app looks for the real
  `C:\Windows\Fonts\comic.ttf` (and `comicbd.ttf` for bold) on the machine
  it's running on and embeds those. We don't bundle Comic Sans MS in this
  repo ourselves - it's a Microsoft font and redistributing the file isn't
  allowed - but since it's already on essentially every Windows PC, the app
  finds and uses it automatically. If it's ever missing, the PDF falls back
  to a plain built-in font instead of crashing (see `precision_worksheets/fonts.py`).

## Project layout

```
run.py                        entry point - launches the GUI
precision_worksheets/
  generator.py                 word-grid shuffling logic (no UI/file code)
  fonts.py                     finds/registers Comic Sans MS for PDF output
  pdf_export.py                turns sheets into a PDF (reportlab)
  docx_export.py                turns sheets into a Word doc (python-docx)
  gui.py                        the Tkinter window that ties it together
tests/                          unit tests for the generator, fonts and exporters
build_windows_exe.bat           packages the app as a Windows .exe
```

`generator.py` is kept independent of the PDF/Word/GUI code on purpose, so
the same "evenly-shuffled word grid" logic can be reused later for other
practice tools without duplicating the shuffling rules.

## Running the tests

```
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

These cover the word-shuffling logic and both export formats. The GUI
itself was exercised end-to-end in this sandbox using a virtual display
(Xvfb) to drive the real Tkinter widgets and confirm the generate/validate
flow doesn't crash and produces correct files - but it hasn't been visually
checked on an actual Windows desktop yet, so it's worth a quick look once
you have it running there.

## Roadmap

You mentioned wanting to build other practice games later - e.g. a
Snake & Ladders board using the same target words. `generator.py`'s word
shuffling is deliberately separate from the worksheet-specific PDF/Word
code, so a future game can reuse it directly rather than needing its own
copy. That game itself isn't built yet - this project currently covers the
probe-sheet worksheets only.
