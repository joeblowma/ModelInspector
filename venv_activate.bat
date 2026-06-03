@echo off
title ModelInspector VENV

echo ---------------------------------
echo VENV Activate Script (2026-05-04)
echo ---------------------------------
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

echo Activating virtual environment...
call "%VENV_NAME%\Scripts\activate"
echo Virtual environment activated.
echo To deactivate the virtual environment, type 'deactivate'.
cmd /k
