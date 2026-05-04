@echo off

echo --------------------------------------------------------------------------------
echo VENV Cleanup Script - Removes virtual environment data if it exists (2026-05-04)
echo --------------------------------------------------------------------------------
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
:: get rid of the venv created folder
if exist %VENV_NAME% (
    echo deleting %VENV_NAME%
    del /s /q %VENV_NAME%
    rd /s /q %VENV_NAME%
) else (
    echo .\%VENV_NAME% directory not found, moving on
)

:: get rid of the build folder
if exist build (
    echo deleting build
    del /s /q build
    rd /s /q build
) else (
    echo .\build directory not found, moving on
)

:: get rid of the __pycache__ folder
if exist __pycache__ (
    echo deleting __pycache__
    del /s /q __pycache__
    rd /s /q __pycache__
) else (
    echo .\__pycache__ directory not found, moving on
)

:: get rid of venvars.bat
echo deleting venvars.bat
del /q venvars.bat

echo.
echo Done.
pause
exit 0

:errorexit
echo.
echo.
echo.
echo WARINGING: Unexpected error %ERRORLEVEL% occured, aborting.
pause
exit %ERRORLEVEL%

