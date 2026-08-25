@echo off
title ModelInspector Compile

echo -------------------------------------------------
echo ModelInspector - Compilation Script (PyInstaller)
echo -------------------------------------------------
echo.

:: Check for virtual environment var file created by install script
if not exist venvars.bat (
    echo.
    echo.
    echo [ERROR] venvars.bat not found
    echo Run venv_create.bat to get started.
    pause
    exit 1
)
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

:: Ensure pyinstaller is installed
echo [INFO] Verifying PyInstaller installation...
pip show pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] PyInstaller not found in venv. Installing...
    uv pip install pyinstaller
)

:: Ensure Pillow is installed (needed for PNG -> ICO conversion)
pip show pillow >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [INFO] Pillow not found in venv. Installing...
    uv pip install pillow
)

:: Convert icon.png to icon.ico (Windows executables require .ico)
if not exist assets\icon.ico (
    echo [INFO] Converting icon.png to icon.ico...
    python -c "from PIL import Image; img = Image.open('assets/icon.png'); img.save('assets/icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Icon conversion failed.
        pause
        exit 1
    )
)

:: Convert splash_base.png to splash.png (Pyinstaller wants 640x480 from 800x600, may need to update this if base is changed)
if not exist assets\splash.bmp (
    echo [INFO] Converting splash_base.bmp to splash.bmp...
    python assets\ResizeSplash.py assets\splash_base.bmp assets\splash.png 400 600
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Icon conversion failed.
        pause
        exit 1
    )
)

:: Update or create version.txt
if exist assets\GetVersion.py (
    echo [INFO] Updating version.txt
    python assets\GetVersion.py
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Generating version.txt failed.
        pause
        exit 1
    )
)

:: Need to confirm or create ModelInspector.spec
echo [INFO] Starting compilation...
if not exist ModelInspector.spec (
    echo [WARNING] ModelInspector.spec not found! Generating...
    pyi-makespec ^
        --onefile ^
        --windowed ^
        --argv-emulation ^
        --optimize 2 ^
        --name "ModelInspector" ^
        --version-file "version.txt" ^
        --icon "assets/icon.ico" ^
        --add-data "assets/icon.ico:assets" ^
        --add-data "assets/themes/catppuccin.jsonc:assets/themes" ^
        --add-data "assets/themes/cursor.jsonc:assets/themes" ^
        --add-data "assets/themes/github.jsonc:assets/themes" ^
        --add-data "assets/themes/gruvbox.jsonc:assets/themes" ^
        --splash "assets/splash.png" ^
        src/gui.py
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Generating ModelInspector.spec failed.
        pause
        exit 1
    ) else (
        echo [INFO] ModelInspector.spec created!
    )
)

:: Finally, compile the executable
echo [INFO] Building with pyinstaller...
pyinstaller --noconfirm ModelInspector.spec
:: --log-level can be TRACE, DEBUG, INFO, WARN, DEPRECATION, ERROR, FATAL (default: INFO)

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Compilation failed.
    echo error %ERRORLEVEL%
    pause
    exit 1
)

echo.
echo ------------------------------------------------------------------------------
echo SUCCESS: Compilation complete.
echo The executable can be found in the 'dist' folder.
echo ------------------------------------------------------------------------------
pause
