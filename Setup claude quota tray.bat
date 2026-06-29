@echo off
setlocal enabledelayedexpansion
title Claude Quota Tray - Setup

REM Resolve project directory
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

REM Python version to auto-install if not present. Bump this string and the
REM URLs below when a newer release ships. Format: 3.X.Y (must have Windows
REM binary installers -- see https://www.python.org/downloads/windows/).
set "PY_BUNDLED_VER=3.13.13"

echo.
echo ============================================================
echo   Claude Quota Tray  -  Setup
echo ============================================================
echo.
echo   Installing in: %PROJECT_DIR%
echo.

REM ==================================================================
REM [1/4] Locate Python (auto-install if missing)
REM ==================================================================
echo [1/4] Looking for Python...

set "PY_CMD="

REM Try `py` launcher first (handles multi-version, recommended on Windows)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY_CMD=py -3"
)

REM Fall back to plain `python`
if not defined PY_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo   Not found.
    echo.
    echo   Python is required to run this app. The setup can download
    echo   and install Python %PY_BUNDLED_VER% for you ^(~30 MB^).
    echo   It will be installed for your user only ^(no admin needed^).
    echo.
    choice /c YN /n /m "Install Python automatically? [Y/N] "
    echo.
    if errorlevel 2 (
        echo   You can install Python manually from:
        echo     https://www.python.org/downloads/
        echo   Make sure to tick "Add python.exe to PATH" during install,
        echo   then re-run this setup.
        pause
        exit /b 1
    )
    call :install_python
    if not defined PY_CMD (
        echo.
        echo   [ERROR] Python install completed but executable was not found.
        echo   Please close this window, open a new Command Prompt,
        echo   and re-run this setup script.
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%V in ('%PY_CMD% --version 2^>^&1') do echo   Using: %%V
echo.

REM ==================================================================
REM [2/4] Create virtual environment
REM ==================================================================
set "VENV_DIR=%PROJECT_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"

if exist "%VENV_PY%" (
    echo [2/4] Virtual environment already exists -- skipping
) else (
    echo [2/4] Creating virtual environment...
    %PY_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo   [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   Created: %VENV_DIR%
)
echo.

REM ==================================================================
REM [3/4] Install dependencies
REM ==================================================================
echo [3/4] Installing dependencies (may take ~30 sec)...
"%VENV_PY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
if errorlevel 1 (
    echo   [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
)
"%VENV_PY%" -m pip install -r "%PROJECT_DIR%\requirements.txt" --quiet --disable-pip-version-check
if errorlevel 1 (
    echo   [ERROR] Failed to install dependencies.
    echo   Try running this script again, or check your internet connection.
    pause
    exit /b 1
)
echo   Installed packages from requirements.txt ^(incl. pycryptodome on Windows^)
echo.

REM ==================================================================
REM [4/4] Create Startup shortcut
REM ==================================================================
echo [4/4] Creating Windows Startup shortcut...

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT=%STARTUP_DIR%\Claude Quota Tray.lnk"
set "MAIN_SCRIPT=%PROJECT_DIR%\src\main.py"
set "APP_EXE=%PROJECT_DIR%\dist\ClaudeQuotaTray.exe"
set "APP_ICON=%PROJECT_DIR%\assets\app.ico"

set "VBS_TEMP=%TEMP%\cqt_make_shortcut_%RANDOM%.vbs"

> "%VBS_TEMP%" echo Set ws = CreateObject("WScript.Shell")
>> "%VBS_TEMP%" echo Set s = ws.CreateShortcut("%SHORTCUT%")
if exist "%APP_EXE%" (
    echo   Using built .exe for startup shortcut ^(custom taskbar icon^).
    >> "%VBS_TEMP%" echo s.TargetPath = "%APP_EXE%"
    >> "%VBS_TEMP%" echo s.Arguments = ""
) else (
    echo   No dist\ClaudeQuotaTray.exe — shortcut uses pythonw ^(taskbar may show Python^).
    echo   Run build.bat after setup for the custom icon on the taskbar.
    >> "%VBS_TEMP%" echo s.TargetPath = "%VENV_PYW%"
    >> "%VBS_TEMP%" echo s.Arguments = """%MAIN_SCRIPT%"""
)
>> "%VBS_TEMP%" echo s.WorkingDirectory = "%PROJECT_DIR%"
>> "%VBS_TEMP%" echo s.WindowStyle = 7
>> "%VBS_TEMP%" echo s.Description = "Claude Quota Tray - shows Claude usage in the system tray"
if exist "%APP_ICON%" (
    >> "%VBS_TEMP%" echo s.IconLocation = "%APP_ICON%,0"
)
>> "%VBS_TEMP%" echo s.Save

cscript //nologo "%VBS_TEMP%" >nul 2>&1
del "%VBS_TEMP%" >nul 2>&1

if exist "%SHORTCUT%" (
    echo   Shortcut created: %SHORTCUT%
    echo   The app will start automatically next time Windows boots.
) else (
    echo   [WARN] Could not create startup shortcut automatically.
    echo   You can still run the app manually with "Run claude quota tray.bat".
)
echo.

echo ============================================================
echo   Setup complete!
echo ============================================================
echo.

choice /c YN /n /m "Start Claude Quota Tray now? [Y/N] "
echo.

if errorlevel 2 goto :end_no_launch

echo Starting...
if exist "%APP_EXE%" (
    start "" "%APP_EXE%"
) else (
    start "" "%VENV_PYW%" "%MAIN_SCRIPT%"
)
echo The tray icon should appear shortly in the bottom-right of your screen.
echo If you don't see it, click the up-arrow to show hidden icons.
echo.
echo You can close this window.
goto :end

:end_no_launch
echo You can start it any time by double-clicking "Run claude quota tray.bat".

:end
echo.
pause
endlocal
exit /b 0


REM ==================================================================
REM SUBROUTINE: install_python
REM   Downloads the official python.org installer and runs it silently
REM   in per-user mode (no admin needed). Sets PY_CMD on success.
REM ==================================================================
:install_python
    REM Pick architecture-specific installer URL
    set "PY_ARCH_SUFFIX=-amd64"
    if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "PY_ARCH_SUFFIX=-arm64"
    if /i "%PROCESSOR_ARCHITECTURE%"=="x86" (
        if /i not "%PROCESSOR_ARCHITEW6432%"=="AMD64" set "PY_ARCH_SUFFIX="
    )

    set "PY_INSTALLER_NAME=python-%PY_BUNDLED_VER%%PY_ARCH_SUFFIX%.exe"
    set "PY_URL=https://www.python.org/ftp/python/%PY_BUNDLED_VER%/%PY_INSTALLER_NAME%"
    set "PY_INSTALLER=%TEMP%\%PY_INSTALLER_NAME%"

    echo.
    echo   Downloading %PY_INSTALLER_NAME% ...
    echo   From: %PY_URL%

    REM Prefer curl (built into Windows 10 1803+, shows a progress bar).
    REM Fall back to PowerShell's Invoke-WebRequest for older systems.
    where curl >nul 2>&1
    if not errorlevel 1 (
        curl -L --fail -o "%PY_INSTALLER%" "%PY_URL%"
    ) else (
        powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%' -UseBasicParsing"
    )

    if not exist "%PY_INSTALLER%" (
        echo.
        echo   [ERROR] Download failed.
        echo   Please check your internet connection, then install Python
        echo   manually from https://www.python.org/downloads/
        start "" https://www.python.org/downloads/
        goto :eof
    )

    echo   Download OK.
    echo.
    echo   Installing Python (this takes ~1 minute, please wait)...

    REM Silent install, per-user, add to PATH, include py launcher.
    REM    /quiet            - no UI
    REM    InstallAllUsers=0 - per-user (no admin / UAC needed)
    REM    PrependPath=1     - prepend Scripts and install dir to PATH
    REM    Include_test=0    - skip test suite (saves ~25 MB)
    REM    Include_launcher=1- install the `py` launcher
    "%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1

    if errorlevel 1 (
        echo   [ERROR] Python installer returned an error.
        del "%PY_INSTALLER%" >nul 2>&1
        goto :eof
    )

    del "%PY_INSTALLER%" >nul 2>&1
    echo   Install OK.
    echo.

    REM PATH in *this* cmd session is still stale, so locate the new
    REM python.exe directly. Per-user installs land under:
    REM   %LOCALAPPDATA%\Programs\Python\Python3XX\python.exe
    REM Pick the highest-numbered match.
    set "FOUND_PY="
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" set "FOUND_PY=%%D\python.exe"
    )

    if defined FOUND_PY (
        set PY_CMD="!FOUND_PY!"
        echo   Detected new install at: !FOUND_PY!
    )
    goto :eof
