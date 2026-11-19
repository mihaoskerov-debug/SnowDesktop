@echo off
rem Builds a single SnowDesktop.exe (no Python needed on the target PC).
rem Result: dist\SnowDesktop.exe
cd /d "%~dp0"
python -m pip install --upgrade pip pyinstaller PySide6
if errorlevel 1 goto fail
if not exist snow.ico python make_icon.py
set ICON=
if exist snow.ico set ICON=--icon snow.ico
python -m PyInstaller --noconsole --onefile --name SnowDesktop %ICON% snow.pyw
if errorlevel 1 goto fail
echo.
echo Done: dist\SnowDesktop.exe
pause
exit /b 0
:fail
echo.
echo Build failed. See messages above.
pause
exit /b 1
