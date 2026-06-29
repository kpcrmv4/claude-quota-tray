@echo off
REM Manual launcher. Prefers dist\ClaudeQuotaTray.exe (custom icon on taskbar).
REM Falls back to pythonw + src\main.py for dev/source-only installs.

setlocal

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "APP_EXE=%PROJECT_DIR%\dist\ClaudeQuotaTray.exe"
set "VENV_PYW=%PROJECT_DIR%\.venv\Scripts\pythonw.exe"
set "MAIN_SCRIPT=%PROJECT_DIR%\src\main.py"

if exist "%APP_EXE%" (
    start "" "%APP_EXE%"
    endlocal
    exit /b 0
)

if not exist "%VENV_PYW%" (
    echo The app has not been installed yet.
    echo Run "Setup claude quota tray.bat" or build with build.bat first.
    echo.
    pause
    exit /b 1
)

if not exist "%MAIN_SCRIPT%" (
    echo Cannot find src\main.py
    pause
    exit /b 1
)

echo Note: Running via pythonw — taskbar may show the Python icon.
echo After build.bat, use dist\ClaudeQuotaTray.exe for the custom icon.
start "" "%VENV_PYW%" "%MAIN_SCRIPT%"
endlocal
