:: Remove the virtual environment
:: Version 1.6
@echo off
title ModelInspector VENV Delete

echo -------------------------------------------------------------------
echo VENV Cleanup Script - Removes virtual environment data if it exists
echo -------------------------------------------------------------------
echo.

:: Check for virtual environment var file created by install script
if not exist venvars.bat (
    echo.
    echo.
    echo ERROR: venvars.bat not found
    echo Run venv_create.bat to get started.
    pause
    exit 1
)
call venvars.bat

setlocal enabledelayedexpansion

echo Environment "%VENV_NAME%" at:
echo %VENV_PATH%
echo.

:: make sure execution was intentional
set /p DELETE_ALL="Do you REALLY want to clean this environment? (Y/N) (Enter for 'N'): "
if not defined DELETE_ALL (set DELETE_ALL=N)
if /I "!DELETE_ALL!"=="Y" (
    goto startcleanup
) else (
    echo.
    echo.
    echo Aborted. Nothing has been touched, exiting now.
    exit 1
)

:startcleanup
:: clean up directories
for %%P in (
    "%VENV_NAME%"
    "build"
) do (
    if exist "%%~P" (
        echo Deleting directory %%~P
        rmdir /s /q %%~P
    ) else (
        echo %%~P not found, moving on
    )
)

:: get rid of venvars.bat
:: no need to exist this one, it's the gate to the script
echo deleting venvars.bat
del /f /q ".\venvars.bat"

echo.
echo ------------------------------------------------------------------------------
echo DONE: Build VENV cleanup finished.
echo ------------------------------------------------------------------------------
pause

exit 0
