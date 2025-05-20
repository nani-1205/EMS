@echo off
echo Building Monitoring Agent EXE with explicit hidden imports...
echo.

REM Get the directory of this batch script
SET "SCRIPT_DIR=%~dp0"
REM Navigate to the script's directory (where agent.py and requirements.txt should be)
cd /D "%SCRIPT_DIR%"

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python does not seem to be installed or in PATH.
    pause
    exit /b 1
)

REM Check if pip is available
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pip does not seem to be installed or in PATH.
    pause
    exit /b 1
)

REM Activate virtual environment if it exists and user wants to use it
REM This part is optional; if you always build from global Python, you can remove it.
IF EXIST "venv\Scripts\activate.bat" (
    echo Found virtual environment 'venv'.
    REM choice /C YN /M "Activate virtual environment (venv)?"
    REM IF ERRORLEVEL 2 goto SkipVenv
    echo Activating virtual environment...
    call "venv\Scripts\activate.bat"
    echo Virtual environment activated.
    :SkipVenv
) ELSE (
    echo No 'venv' virtual environment found in current directory. Proceeding with current Python environment.
)
echo.

echo Installing/Updating build tools (PyInstaller) and key dependencies (pywin32, psutil)...
pip install --upgrade pyinstaller pywin32 psutil
if %errorlevel% neq 0 (
    echo ERROR: Failed to install/update build tools or key dependencies.
    pause
    exit /b 1
)
echo.

echo Installing agent dependencies from requirements.txt...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install agent dependencies from requirements.txt.
    pause
    exit /b 1
)
echo.

echo Starting PyInstaller build...
REM --- PyInstaller Command with Hidden Imports ---
REM --onefile: Creates a single executable file
REM --windowed: Prevents the console window from appearing (same as --noconsole)
REM --name: Specifies the name of the output executable
REM --clean: Clean PyInstaller cache and remove temporary files before building.
REM --log-level: Can be DEBUG, INFO, WARN, ERROR, CRITICAL (INFO is default)
REM Add --upx-dir C:\path\to\upx if you want to use UPX for compression (makes exe smaller but can sometimes cause AV flags)

pyinstaller --onefile --windowed --name monitoring_agent ^
--clean ^
--log-level INFO ^
--hidden-import=win32timezone ^
--hidden-import=win32ctypes.core ^
--hidden-import=win32ctypes.pywin32_system32 ^
--hidden-import=win32gui ^
--hidden-import=win32process ^
--hidden-import=win32event ^
--hidden-import=win32api ^
--hidden-import=win32com ^
--hidden-import=win32com.client ^
--hidden-import=win32clipboard ^
--hidden-import=win32con ^
--hidden-import=win32cred ^
--hidden-import=win32evtlog ^
--hidden-import=win32file ^
--hidden-import=win32net ^
--hidden-import=win32profile ^
--hidden-import=win32security ^
--hidden-import=win32service ^
--hidden-import=win32serviceutil ^
--hidden-import=win32transaction ^
--hidden-import=win32ts ^
--hidden-import=win32wnet ^
--hidden-import=pywintypes ^
--hidden-import=pythoncom ^
--hidden-import=psutil ^
--hidden-import=psutil._psutil_windows ^
--hidden-import=psutil._pswindows ^
--hidden-import=psutil._psutil_common ^
--hidden-import=pkg_resources.py2_warn ^
--hidden-import=PIL._tkinter_finder ^
agent.py

REM Check if build was successful
if %errorlevel% neq 0 (
    echo.
    echo ********************
    echo *** BUILD FAILED ***
    echo ********************
    echo Check the output above for specific PyInstaller errors.
    pause
    exit /b %errorlevel%
)

echo.
echo ************************
echo *** BUILD SUCCESSFUL ***
echo ************************
echo EXE created in the 'dist' folder: dist\monitoring_agent.exe
echo.

REM Optional: Deactivate virtual environment if it was used
REM IF "%VIRTUAL_ENV%" NEQ "" (
REM    echo Deactivating virtual environment...
REM    call "venv\Scripts\deactivate.bat"
REM )

pause