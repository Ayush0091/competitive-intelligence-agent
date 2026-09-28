@echo off
REM One-click: set up, verify your local Ollama/Qwen model, run the tests and
REM generate the LIVE sample transcripts in examples\live_run_0*.md
cd /d "%~dp0"

where python >nul 2>nul || (echo Python not found on PATH. Install Python 3.11+ first. & pause & exit /b 1)

if not exist .venv (
  echo [setup] Creating virtual environment...
  python -m venv .venv || (echo Failed to create venv & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
echo [setup] Installing requirements...
python -m pip install -q -r requirements.txt || (echo pip install failed & pause & exit /b 1)

if not exist .env (
  copy .env.example .env >nul
  echo [setup] Created .env from .env.example  ^(OLLAMA_MODEL=auto picks your Qwen model^)
)

echo.
echo [1/3] Checking the local LLM (Ollama)...
python main.py --check-llm
if errorlevel 1 (
  echo.
  echo LLM check failed. Make sure the Ollama app is running and `ollama list` shows your model.
  echo You can pin the model in .env, e.g.  OLLAMA_MODEL=qwen2.5:7b
  pause
  exit /b 1
)

echo.
echo [2/3] Running the test suite...
python -m pytest || (echo Tests failed - see output above. & pause & exit /b 1)

echo.
echo [3/3] Generating LIVE transcripts (real web data + your local model). This can take a while...
python scripts\make_examples.py --live

echo.
echo Done. Open the examples\ folder: live_run_01_normal.md, live_run_02_comparison.md,
echo live_run_03_failure_recovery.md. Full reports are also in the runs\ folder.
pause
