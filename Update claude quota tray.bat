@echo off
setlocal enabledelayedexpansion
title Claude Quota Tray - Update

REM Resolve project directory
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "VENV_DIR=%PROJECT_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"
set "MAIN_SCRIPT=%PROJECT_DIR%\src\main.py"

echo.
echo ============================================================
echo   Claude Quota Tray  -  Update
echo ============================================================
echo.
echo   Project: %PROJECT_DIR%
echo.

REM ==================================================================
REM Sanity check: app must already be installed
REM ==================================================================
if not exist "%VENV_PY%" (
    echo   [ERROR] Virtual environment not found.
    echo.
    echo   This script only refreshes an existing install.
    echo   For a first-time install, run "Setup claude quota tray.bat"
    echo   instead.
    echo.
    pause
    exit /b 1
)

if not exist "%MAIN_SCRIPT%" (
    echo   [ERROR] src\main.py not found.
    echo   Make sure you've extracted/replaced the source files first.
    echo.
    pause
    exit /b 1
)

REM ==================================================================
REM [1/3] Stop the running instance, if any.
REM ==================================================================
REM We use a temp PowerShell script to find ONLY pythonw.exe processes
REM whose command line references this project's main.py -- so other
REM Python apps the user has running are left alone.
echo [1/3] Stopping running instance ^(if any^)...

set "PS_TEMP=%TEMP%\cqt_stop_%RANDOM%.ps1"

> "%PS_TEMP%" echo $target = "%MAIN_SCRIPT%"
>> "%PS_TEMP%" echo $procs = @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue ^| Where-Object { $_.CommandLine -like "*$target*" })
>> "%PS_TEMP%" echo if ($procs.Count -gt 0) {
>> "%PS_TEMP%" echo     $procs ^| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
>> "%PS_TEMP%" echo     Write-Host "  Stopped $($procs.Count) running instance(s)."
>> "%PS_TEMP%" echo } else {
>> "%PS_TEMP%" echo     Write-Host "  No running instance found."
>> "%PS_TEMP%" echo }

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_TEMP%"
del "%PS_TEMP%" >nul 2>&1

REM Give Windows a moment to release the tray icon slot
timeout /t 1 /nobreak >nul 2>&1
echo.

REM ==================================================================
REM [2/3] Download latest release from GitHub and refresh deps
REM ==================================================================
echo [2/3] Updating from GitHub ^(see settings: update_github_repo^)...

set "UPDATE_RUNNER=%PROJECT_DIR%\src\update_runner.py"
if not exist "%UPDATE_RUNNER%" (
    echo   [ERROR] src\update_runner.py not found.
    pause
    exit /b 1
)

"%VENV_PY%" "%UPDATE_RUNNER%" --apply
if errorlevel 1 (
    echo.
    echo   [ERROR] GitHub update failed.
    echo   Check internet, repo name in tray menu - Install/update - Update source,
    echo   or publish a release on GitHub with a source .zip asset.
    pause
    exit /b 1
)

echo   Done.
echo.

REM ==================================================================
REM [3/3] Restart ^(update_runner starts the app when successful^)
REM ==================================================================
echo [3/3] Restart...
if not exist "%MAIN_SCRIPT%" (
    echo   Source update complete. Start manually with "Run claude quota tray.bat"
) else (
    echo   If the tray icon did not appear, run "Run claude quota tray.bat".
)
echo.

echo ============================================================
echo   Update complete!
echo ============================================================
echo.
echo The tray icon should appear shortly in the bottom-right.
echo If you don't see it, click the up-arrow to show hidden icons.
echo.
echo You can close this window.
echo.
pause
endlocal
exit /b 0
