@echo off
rem Builds a single SnowWidgets.exe (desktop widgets, no Python needed on the target PC).
rem Result: dist\SnowWidgets.exe
cd /d "%~dp0"
python -m pip install --upgrade pip pyinstaller PySide6
if errorlevel 1 goto fail
python -m PyInstaller --noconsole --onefile --name SnowWidgets widgets.pyw
if errorlevel 1 goto fail
echo.
echo Done: dist\SnowWidgets.exe
pause
exit /b 0
:fail
echo.
echo Build failed. See messages above.
pause
exit /b 1
