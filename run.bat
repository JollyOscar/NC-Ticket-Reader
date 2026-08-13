@echo off
setlocal

cd /d "%~dp0"
title Nova Construction Ticket App Launcher

echo ==========================================
echo   Nova Construction Ticket App Launcher
echo ==========================================
echo.

if not exist ".venv\Scripts\activate.bat" (
	echo [ERROR] Python virtual environment was not found at ".venv".
	echo.
	echo Please set up the virtual environment:
	echo   py -m venv .venv
	echo   call .venv\Scripts\activate
	echo   pip install -r requirements.txt
	echo.
	pause
	exit /b 1
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
	echo [ERROR] Failed to activate virtual environment.
	pause
	exit /b 1
)

if not defined OCR_PROVIDER set "OCR_PROVIDER=easyocr"

echo Launching app on http://localhost:8501 ...
start "" "http://localhost:8501"
python -m streamlit run app.py

endlocal
