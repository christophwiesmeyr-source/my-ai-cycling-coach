@echo off
REM Quick start script for My AI Cycling Coach (Windows)

echo.
echo 🚀 My AI Cycling Coach - Setup
echo ================================

REM Check Python version
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    exit /b 1
)

python --version
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔄 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
pip install -q -r requirements.txt

echo.
echo ✅ Setup complete!
echo.
echo 📝 To run the application:
echo    venv\Scripts\activate.bat
echo    python main.py
echo.
echo 💡 To load FIT files:
echo    1. Copy .fit files to the 'data\' directory, or
echo    2. Click 'Open Folder' in the application
echo.
pause
