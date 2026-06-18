:: Guides the user through a virtual environment creation process
:: Version 1.6
@echo off
title ModelInspector VENV Install
set USE_PYTHON_VER=3.11

echo ------------------------
echo VENV Installation Script
echo ------------------------
echo.

:: Check for virtual environment var file created by install script
if exist venvars.bat (
    echo.
    echo.
    echo ERROR: venvars.bat found
    echo Aborting, virtual environment may already exist
    echo Run venv_delete.bat first or remove venvars.bat and the virtual env folder
    echo and try again.
    pause
    exit 1
)

uv.exe --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo.
    echo ERROR: uv not found! Aborting!
    echo.
    echo Run one of the following:
    echo - powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo - pip install uv
    echo - pipx install uv
    echo or go to https://github.com/astral-sh/uv for more ways to install
    echo.
    echo then try venv_create.bat again.
    pause
    exit 1
)


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

:: Create the virtual environment
echo Creating virtual environment '!VENV_NAME!' with python v%USE_PYTHON_VER% at:
echo !VENV_PATHED!
uv venv --relocatable --prompt !VENV_NAME! --python %USE_PYTHON_VER% --python-preference only-managed !VENV_NAME!
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

:: Activate the virtual environment
echo ----------------------------
echo Activate virtual environment
echo ----------------------------
call "!VENV_PATHED!\Scripts\activate"
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo Done.
echo.

:: Install pip
echo -----------
echo Install pip
echo -----------
echo Installing pip...
uv pip install pip
IF %ERRORLEVEL% NEQ 0 (goto errorexit)
echo Done.
echo.

:: Check if requirements.txt exists and handle installation
if exist requirements.txt (
    echo.
    echo -----------------------------------------
    echo Installing dependencies from requirements
    echo -----------------------------------------
    :: Prompt the user for installation of requirements.txt
    set /p INSTALL_REQUIREMENTS="Do you wish to install modules in 'requirements.txt'? (Y/N) (Press Enter for default 'Y'): "

    if not defined INSTALL_REQUIREMENTS (set INSTALL_REQUIREMENTS=Y)
    if /I "!INSTALL_REQUIREMENTS!"=="Y" (
        echo Installing requirements.txt modules...
        uv pip install -r requirements.txt
        IF %ERRORLEVEL% NEQ 0 (goto errorexit)
        echo Done.
    ) else (
        echo Skipping requirements.txt installation.
        goto skipreqs
    )
) else (
    echo requirements.txt not found. Skipping requirements installation.
    goto skipreqs
)
echo.

:: Check if requirements-dev.txt exists and handle installation
if exist requirements-dev.txt (
    echo.
    echo --------------------------------------------
    echo Installing dependencies for requirements-dev
    echo --------------------------------------------
    :: Prompt the user for installation of requirements-dev.txt
    set /p INSTALL_REQUIREMENTS="Do you wish to install modules in 'requirements-dev.txt'? (Y/N) (Press Enter for default 'Y'): "

    if not defined INSTALL_REQUIREMENTS (set INSTALL_REQUIREMENTS=Y)
    if /I "!INSTALL_REQUIREMENTS!"=="Y" (
        echo Installing requirements-dev.txt modules...
        uv pip install -r requirements-dev.txt
        IF %ERRORLEVEL% NEQ 0 (goto errorexit)
        echo Done.
    ) else (
        echo Skipping requirements-dev installation.
    )
) else (
    echo requirements-dev.txt not found. Skipping requirements-dev installation.
)

:skipreqs
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
