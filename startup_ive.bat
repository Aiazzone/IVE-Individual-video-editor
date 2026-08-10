@echo off
setlocal EnableExtensions
rem ============================================================
rem  IVE - Individual Video Editor : Windows launcher
rem
rem  Works from any directory and with any drive letter.
rem  Interpreter search order:
rem    1. %IVE_PYTHON%            explicit override
rem    2. .venv next to this file (per-project environment)
rem    3. shared venv, four levels up (the usual setup here)
rem    4. python on PATH
rem
rem  Arguments are passed straight through, e.g.:
rem    startup_ive.bat --lang it
rem ============================================================

cd /d "%~dp0"

rem Windows consoles default to cp1252; the logs and locale files are UTF-8.
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

set "PY="

if defined IVE_PYTHON (
    if exist "%IVE_PYTHON%" set "PY=%IVE_PYTHON%"
)

if not defined PY (
    if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
)

if not defined PY (
    if exist "%~dp0..\..\..\..\.venv\Scripts\python.exe" (
        for %%I in ("%~dp0..\..\..\..\.venv\Scripts\python.exe") do set "PY=%%~fI"
    )
)

if not defined PY (
    where python.exe >nul 2>&1 && set "PY=python.exe"
)

if not defined PY (
    echo(
    echo   [IVE] No Python interpreter found.
    echo(
    echo   Looked for:
    echo     - %%IVE_PYTHON%%
    echo     - %~dp0.venv\Scripts\python.exe
    echo     - %~dp0..\..\..\..\.venv\Scripts\python.exe
    echo     - python.exe on PATH
    echo(
    echo   Set one explicitly and try again:
    echo     set IVE_PYTHON=C:\path\to\python.exe
    echo(
    pause
    exit /b 9009
)

echo [IVE] Interpreter: %PY%
"%PY%" "%~dp0startup_ive.py" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo(
    echo   [IVE] Exited with code %RC%.
    echo   Details are in: %~dp0user_data\log\ive.log
    echo(
    pause
)

endlocal & exit /b %RC%
