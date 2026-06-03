:: Guides the user through a virtual environment creation process
:: Version 1.6
@echo off
title ModelInspector VENV Install

echo ------------------------------------------------------------------------------
echo VENV Installation Script - Helps you create a virtual environment (2026-05-04)
echo ------------------------------------------------------------------------------
echo.

:: Temporarily disable delayed expansion to check for "!" in the path
setlocal disabledelayedexpansion
echo You are about to create a virtual environment in: %CD%
set "CURRENT_PATH=%CD%"
set "MODIFIED_PATH=%CURRENT_PATH:!=%"
if not "%CURRENT_PATH%"=="%MODIFIED_PATH%" (
    echo WARNING: The current directory contains a "!" character, which may cause issues. Running 'pip install -r requirements' may have trouble installing. Proceed at your own risk.
)
endlocal
setlocal enabledelayedexpansion


:: Initialize counter
set COUNT=0

:: Parse the output of py -0p
for /f "tokens=1,*" %%a in ('py -0p') do (
    :: Filter lines that start with a dash, indicating a Python version, and capture the path
    echo %%a | findstr /R "^[ ]*-" > nul && (
        set /a COUNT+=1
        set "pythonVersion=%%a"

        set "pythonVersion=!pythonVersion:*V:=!"   :: remove leading -V:
        for /f "tokens=1 delims=[]" %%v in ("!pythonVersion!") do set "pythonVersion=%%v"

        set "PYTHON_VER_!COUNT!=!pythonVersion!"
        set "PYTHON_PATH_!COUNT!=%%b"  :: Store the path in a separate variable
    )
)
IF %ERRORLEVEL% NEQ 0 (goto errorexit)

:: Make sure at least one Python version was found
if !COUNT! == 0 (
    echo No Python installations found via Python Launcher. Exiting.
    goto exit
)

echo.
echo --------------
echo Python Version
echo --------------
echo Please choose which of your installed python versions to use:
for /L %%i in (1,1,!COUNT!) do (
    echo %%i. -V:!PYTHON_VER_%%i! at !PYTHON_PATH_%%i!
)
echo.

:: Prompt user to select a Python version (default is 1)
set /p PYTHON_SELECTION="Select a Python version by number (Press Enter for default = '1'): "
if "!PYTHON_SELECTION!"=="" set PYTHON_SELECTION=1

:: Extract the selected Python version tag and parse the version number more accurately
set "SELECTED_PYTHON_VER=!PYTHON_VER_%PYTHON_SELECTION%!"

echo Using Python version !SELECTED_PYTHON_VER!
echo.

:: Prompt for virtual environment name with default 'venv'
echo ------------------------
echo Virtual Environment Name
echo ------------------------
echo Select the name of your virtual environment. Using the default 'venv' is fine.
set VENV_NAME=.venv
set /p VENV_NAME="Enter the name for your virtual environment (Press Enter for default '.venv'): "
if "!VENV_NAME!"=="" set VENV_NAME=%CD%\.venv
set VENV_PATHED=%CD%\!VENV_NAME!
echo.

:: Create the virtual environment using the selected Python version
echo Creating virtual environment '!VENV_NAME!' at:
echo !VENV_PATHED!
py -!SELECTED_PYTHON_VER! -m venv !VENV_PATHED!
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo Done.
echo.

:: Add .gitignore to the virtual environment folder
echo Creating .gitignore in the !VENV_NAME! folder...
(
    echo # Ignore all content in the virtual environment directory
    echo *
    echo # Except this file
    echo !.gitignore
) > !VENV_PATHED!\.gitignore
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo Done.
echo.

:: Generate venvars.bat
echo Generating venvars.bat...
(
    echo @echo off
    echo cd %%~dp0
    echo set VENV_NAME=!VENV_NAME!
    echo set VENV_PATH=!VENV_PATHED!
) > venvars.bat
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo Done.
echo.

:: Activate the virtual environment and upgrade pip
echo ---------------------
echo Upgrading pip install
echo ---------------------
echo Activating virtual environment...
call "!VENV_PATHED!\Scripts\activate"
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo Done.
echo.
echo Upgrading pip...
"!VENV_PATHED!\Scripts\python.exe" -m pip install --upgrade pip
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo Done.
echo.

:: uv pip package installer
echo ------------------------
echo uv pip package installer
echo ------------------------
echo Installing 'uv' package...
pip install uv
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo Done.
echo.

:: Check if requirements.txt exists and handle installation
echo.
echo ---------------------------------------------
echo Installing dependencies from requirements.txt
echo ---------------------------------------------
:: Prompt the user for installation of requirements.txt
if exist requirements.txt (
    echo requirements.txt found.

    set /p INSTALL_REQUIREMENTS="Do you wish to run 'uv pip install -r requirements.txt'? (Y/N) (Press Enter for default 'Y'): "

    if not defined INSTALL_REQUIREMENTS (set INSTALL_REQUIREMENTS=Y)
    if /I "!INSTALL_REQUIREMENTS!"=="Y" (
        echo Installing requirements.txt modules...
        uv pip install -r requirements.txt
        IF %ERRORLEVEL% NEQ 0 (goto errorexit)
        echo Done.
    ) else (
        echo Skipping requirements installation.
    )
) else (
    echo requirements.txt not found. Skipping requirements installation.
)
echo.

:: List installed packages
echo Listing installed packages...
pip list
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo.

echo Setup complete. Your virtual environment is ready.
echo To deactivate the virtual environment, type 'deactivate'.

:: Keep the command prompt open
cmd /k
goto exit

:errorexit
echo.
echo.
echo.
echo WARINGING: Unexpected error %ERRORLEVEL% occured, aborting.
pause
exit %ERRORLEVEL%


:exit
endlocal
exit 0
