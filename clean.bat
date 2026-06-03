:: Clean up files created by compile.bat
:: Version 1.6
@echo off
title ModelInspector Compile Clean

echo -------------------------------------------
echo ModelInspector - Compile.bat Cleanup Script
echo -------------------------------------------
echo.

if not exist ModelInspector.spec (
        echo [ERROR] Cannot clean without ModelInspector.spec!
        pause
        exit 1
)

:: Check for virtual environment var file created by install script
if not exist venvars.bat (
    echo.
    echo.
    echo [ERROR] venvars.bat not found
    echo Run venv_create.bat to get started.
    pause
    exit 1
)

:: make sure execution was intentional
setlocal enabledelayedexpansion
set /p CLEAN_ALL="Do you REALLY want to clean this environment? (Y/N) (Enter for 'N'): "
if not defined CLEAN_ALL (set CLEAN_ALL=N)
if /I "!CLEAN_ALL!"=="Y" (
    goto startcleanup
) else (
    echo.
    echo.
    echo Aborted. Nothing has been touched, exiting now.
    exit 1
)

:startcleanup
endlocal

call venvars.bat

setlocal enabledelayedexpansion

:: Check for virtual environment
if not exist "%VENV_NAME%\Scripts\activate.bat" (
    echo [ERROR] Virtual environment '%VENV_NAME%' not found.
    echo Please run 'venv_create.bat' first to set up the environment.
    pause
    exit 1
)

:: Activate virtual environment
echo [INFO] Activating virtual environment...
call "%VENV_NAME%\Scripts\activate.bat"

:: clean up directories
for %%P in (
    ".\src\__pycache__"
    "build"
    "dist"
    ".\src\.model-inspector"
) do (
    if exist "%%~P" (
        echo Deleting directory %%~P
        rmdir /s /q %%~P
    ) else (
        echo %%~P not found, moving on
    )
)

:: clean up generated files
for %%P in (
    "ModelInspector.spec"
    "version.txt"
    ".\assets\splash.png"
    ".\assets\icon.ico"
) do (
    if exist "%%~P" (
        echo Deleting file %%~P
        del /f /q %%~P
    ) else (
        echo %%~P not found, moving on
    )
)

echo.
echo ------------------------------------------------------------------------------
echo DONE: Build cleanup finished.
echo ------------------------------------------------------------------------------
pause
