@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo [ERROR] Python not found. Install Python from python.org with "Add python.exe to PATH" checked. & pause & exit /b 1)
echo [1/3] Installing packages...
python -m pip install --upgrade requests reportlab pypdf pillow holidays openpyxl
if errorlevel 1 (echo [ERROR] Package install failed. Check internet connection. & pause & exit /b 1)
echo.
echo [2/3] Removing old files...
for %%F in (settings_app.py print_now.bat reprint_last.bat settings.bat test_pdf.bat check_data.bat mark_existing_as_printed.bat) do if exist %%F del /q %%F
echo.
echo [3/3] Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcuts.ps1"
echo.
echo Done. Open the desktop icon to start.
pause
