@echo off
rem Christmas tree: double click to start. Updates the app, installs missing libraries, starts the tree.
rem "start.bat --stop" closes it.
cd /d "%~dp0"

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 (
    py -3 launcher.py %*
    goto done
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 (
    python launcher.py %*
    goto done
)

echo Python 3.9 or newer is not installed. Installing it with winget...
winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    py -3 launcher.py %*
    goto done
)
echo.
echo Python could not be installed automatically.
echo Please install it from https://www.python.org/downloads/ (check "Add python.exe to PATH")
echo and start this file again.
start "" https://www.python.org/downloads/windows/
pause
exit /b 1

:done
if errorlevel 1 pause
