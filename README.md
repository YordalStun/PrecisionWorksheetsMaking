# Precision Worksheet Maker

A small local desktop app for creating **Precision Teaching** practice
materials from the same 5 target words: a probe sheet for fluency
practice, plus four printable games. Enter a child's first name and 5
words once, and generate any of the five as a printable **PDF** and/or
**Word (.docx)** file, ready to print in bulk.

## The five activities

### Probe sheets

The "see it, say it" fluency practice grid, inspired by the layout of
[Worksheet Genius's Precision Teaching
generator](https://worksheetgenius.com/design/precision-worksheet/). Each
page has:

- A header with the child's name, the date, and the sheet number
- (Optional) the list of the 5 target words for reference
- A grid of big, roomy cells (5 columns x 4 rows by default, adjustable)
  filled with the 5 words, repeated evenly and shuffled so no two
  neighbouring cells hold the same word - each sheet in a batch is
  shuffled differently, so re-using the pack doesn't let a child memorise
  the order
- Rows padded to stretch down and fill the page, with the word text sized
  as large as it can be without needing to wrap - if a word is still too
  wide for its box (a long word, or a grid with lots of columns), that
  sheet's font shrinks just enough to fit rather than spilling over the
  lines
- Row numbers down the left edge, so you can count how far the child got
- A scoring line at the bottom: time taken, number correct, number of
  errors, and correct-per-minute

### Matching pairs game

A sheet of big cut-out cards - each of the 5 words appears on exactly two
cards, filling as much of the page as it can. Cut them out, shuffle,
lay them face down, and take turns flipping two at a time looking for a
match - say the word out loud as you flip it.

### Snakes & Ladders

A full 100-square board with ladders to climb and snakes to slide down,
plus a handful of squares showing one of the target words instead of a
number - land on one and read it out loud for a bonus roll. Needs a die
and a counter per player, which the app doesn't provide.

### Bingo

Each card is a shuffled 4x4 grid of the 5 words (so every word appears a
few times per card, in a different arrangement on every card). Call out
words one at a time - from the same 5-word list - and cross off every
matching cell; first to complete a full line, across, down, or diagonal,
shouts BINGO! Generates as many cards as you ask for, one per page.

### Word Search

The 5 words hidden in a grid of letters, reading across, down, or
diagonally down-right (no backwards or upside-down words, to keep it
approachable for early readers). The grid grows automatically to fit
longer words. A quieter, independent activity - find and circle each
word, then check it off the list underneath.

Everything is set in **Comic Sans MS** (see the Fonts section below) for
a friendly, easy-to-read look.

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
2. Enter the child's first name, the 5 words, and tick PDF and/or Word.
3. Pick a tab - **Probe Sheets**, **Matching Pairs Game**, **Snakes &
   Ladders**, **Bingo**, or **Word Search** - adjust that activity's
   options if you want, and click its Generate button.
4. Choose (or accept the default) output folder - it defaults to
   `Documents\PrecisionWorksheets`.
5. The file(s) appear in that folder, ready to print. You can switch tabs
   and generate the other activities from the same name/words without
   re-entering them.

## Fonts

Every page is set in **Comic Sans MS**. It's a standard Windows font (has
shipped with every edition of Windows since 3.1), so:

- **Word (.docx) files** just reference it by name - Word uses whatever
  copy is already installed on the PC that opens the file, which on
  Windows is always the real thing.
- **PDF files**, and the Snakes & Ladders board image, need an actual font
  *file* at the point they're built. The app looks for the real
  `C:\Windows\Fonts\comic.ttf` (and `comicbd.ttf` for bold) on the machine
  it's running on and uses those. We don't bundle Comic Sans MS in this
  repo ourselves - it's a Microsoft font and redistributing the file isn't
  allowed - but since it's already on essentially every Windows PC, the app
  finds it automatically. If it's ever missing: PDF text falls back to a
  plain built-in font, and the board image falls back to a bundled copy of
  [Comic Neue](https://github.com/crozynski/comicneue) (a free, open-licence
  Comic Sans lookalike - see `precision_worksheets/assets/fonts/OFL.txt`),
  rather than either one crashing (see `precision_worksheets/fonts.py`).

## Project layout

```
run.py                            entry point - launches the GUI
precision_worksheets/
  generator.py                     word-grid shuffling logic (no UI/file code)
  fonts.py                         finds Comic Sans MS, or the bundled fallback
  layout.py                        sizes the grid font to fill (not overflow) a box
  pdf_export.py                    probe sheets -> PDF (reportlab)
  docx_export.py                    probe sheets -> Word doc (python-docx)
  docx_helpers.py                  shared python-docx table helpers
  gui.py                            the Tkinter window that ties it together
  games/
    pairs_cards.py                  matching-pairs game -> PDF/Word
    snakes_and_ladders.py           board game (drawn with Pillow) -> PDF/Word
    bingo.py                         bingo cards -> PDF/Word
    word_search.py                   hidden-word puzzle -> PDF/Word
  assets/fonts/                    bundled Comic Neue fallback font + its licence
tests/                              unit tests for the above
build_windows_exe.bat               packages the app as a Windows .exe
```

`generator.py`'s word-grid shuffling is deliberately independent of any
one activity's PDF/Word/GUI code, so the matching-pairs and bingo grids
reuse it directly (each is literally the same function with a different
grid shape / word-repeat count) rather than duplicating the shuffling
rules.

## Running the tests

```
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

These cover the word-shuffling logic, every game's board/card/puzzle
generation (including that every Word Search word is actually findable
in its grid), and all exporters. The GUI itself was exercised end-to-end
in this sandbox using a virtual display (Xvfb) to drive the real Tkinter
widgets and confirm each tab's generate/validate flow doesn't crash and
produces correct files - but it hasn't been visually checked on an
actual Windows desktop yet, so it's worth a quick look once you have it
running there.

## Roadmap

More game ideas were floated (a roll-and-read race track, a spinner
game, snap) but aren't built yet - this covers probe sheets, matching
pairs, Snakes & Ladders, bingo, and word search.
