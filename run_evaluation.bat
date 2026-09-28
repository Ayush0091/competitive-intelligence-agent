@echo off
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo === 1/3 Unit tests ===
python -m pytest -q
echo.
echo === 2/3 Evaluation (labelled fault-injection matrix + guard precision/recall) ===
python scripts\evaluate.py
echo.
echo === 3/3 Monitoring report from saved runs ===
python scripts\monitor.py
echo.
echo Open evaluation\evaluation_report.md and monitoring\dashboard.html
pause
