@echo off
REM Builds a standalone Windows .exe for the Precision Worksheet Maker.
REM
REM Run this file by double-clicking it ON A WINDOWS PC that has Python
REM installed (get it from https://python.org if needed - tick "Add
REM python.exe to PATH" during install). You only need to do this once;
REM after that you can copy PrecisionWorksheetMaker.exe anywhere and run
REM it without Python installed.

setlocal

echo Installing required packages...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo.
echo Building PrecisionWorksheetMaker.exe ...
pyinstaller --noconfirm --onefile --windowed --name "PrecisionWorksheetMaker" ^
    --add-data "precision_worksheets/assets;precision_worksheets/assets" ^
    run.py

echo.
echo Done. Find PrecisionWorksheetMaker.exe inside the "dist" folder.
pause
