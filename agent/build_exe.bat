@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

echo ========================================================
echo == TekPossible Monitor Agent - PyInstaller Build Script ==
echo ========================================================
echo.

REM Get the directory of this batch script
SET "SCRIPT_DIR=%~dp0"
REM Navigate to the script's directory (where agent.py and requirements.txt should be)
echo Changing directory to: %SCRIPT_DIR%
cd /D "%SCRIPT_DIR%"
if errorlevel 1 (
    echo ERROR: Could not change directory to %SCRIPT_DIR%.
    pause
    exit /b 1
)

REM --- Configuration ---
SET PYTHON_EXE=python
SET VENV_NAME=venv
SET OUTPUT_EXE_NAME=monitoring_agent
SET AGENT_SCRIPT_NAME=agent.py
SET REQUIREMENTS_FILE=requirements.txt
SET PYINSTALLER_LOG_LEVEL=INFO

REM --- Check for Python and Pip ---
echo Checking for Python installation...
%PYTHON_EXE% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python interpreter ('%PYTHON_EXE%') not found or not in PATH.
    echo Please ensure Python is installed and added to your system PATH.
    pause
    exit /b 1
)
echo Python found.

echo Checking for pip...
%PYTHON_EXE% -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pip (Python package manager) not found.
    echo It's usually installed with Python. Please check your Python installation.
    pause
    exit /b 1
)
echo pip found.
echo.

REM --- Virtual Environment Handling ---
IF EXIST "%VENV_NAME%\Scripts\activate.bat" (
    echo Virtual environment '%VENV_NAME%' found.
    echo Activating virtual environment...
    call "%VENV_NAME%\Scripts\activate.bat"
    if errorlevel 1 (
        echo ERROR: Failed to activate virtual environment '%VENV_NAME%'.
        pause
        exit /b 1
    )
    echo Virtual environment activated.
) ELSE (
    echo No '%VENV_NAME%' virtual environment found.
    choice /C YN /M "Create a new virtual environment named '%VENV_NAME%' (Recommended)?"
    IF ERRORLEVEL 2 (
        echo Proceeding with current Python environment. Be cautious of global package conflicts.
    ) ELSE (
        echo Creating new virtual environment '%VENV_NAME%'...
        %PYTHON_EXE% -m venv %VENV_NAME%
        if errorlevel 1 (
            echo ERROR: Failed to create virtual environment '%VENV_NAME%'.
            pause
            exit /b 1
        )
        echo Activating new virtual environment...
        call "%VENV_NAME%\Scripts\activate.bat"
        if errorlevel 1 (
            echo ERROR: Failed to activate newly created virtual environment '%VENV_NAME%'.
            pause
            exit /b 1
        )
        echo New virtual environment created and activated.
    )
)
echo.

echo Upgrading pip in the current environment...
python.exe -m pip install --upgrade pip
echo.

echo Installing/Updating core build dependencies (PyInstaller, pywin32, psutil)...
pip install --upgrade pyinstaller pywin32 psutil
if %errorlevel% neq 0 (
    echo ERROR: Failed to install/update PyInstaller, pywin32, or psutil.
    pause
    exit /b 1
)
echo Core build dependencies installed/updated.
echo.

IF EXIST "%REQUIREMENTS_FILE%" (
    echo Installing agent dependencies from %REQUIREMENTS_FILE%...
    pip install -r %REQUIREMENTS_FILE%
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install agent dependencies from %REQUIREMENTS_FILE%.
        pause
        exit /b 1
    )
    echo Agent dependencies installed.
) ELSE (
    echo WARNING: %REQUIREMENTS_FILE% not found. Skipping agent dependency installation.
    echo Ensure all necessary packages (like 'requests', 'Pillow') are manually installed or build might fail.
)
echo.

echo Running pywin32_postinstall script (if available)...
REM This helps ensure pywin32 DLLs are correctly registered/copied
IF EXIST "%VIRTUAL_ENV%\Scripts\pywin32_postinstall.py" (
    python "%VIRTUAL_ENV%\Scripts\pywin32_postinstall.py" -install
) ELSE IF EXIST "%USERPROFILE%\AppData\Local\Programs\Python\Python*\Scripts\pywin32_postinstall.py" (
    REM Attempt to find it in common global Python script locations if not in venv
    FOR /F "delims=" %%i IN ('dir /b /s "%USERPROFILE%\AppData\Local\Programs\Python\Python*\Scripts\pywin32_postinstall.py"') DO (
        echo Found global pywin32_postinstall.py at %%i
        python "%%i" -install
        GOTO FoundPostInstall
    )
    FOR /F "delims=" %%i IN ('dir /b /s "C:\Python*\Scripts\pywin32_postinstall.py"') DO (
         echo Found global pywin32_postinstall.py at %%i
         python "%%i" -install
         GOTO FoundPostInstall
    )
    echo pywin32_postinstall.py not found in typical locations.
    :FoundPostInstall
) ELSE (
     echo pywin32_postinstall.py script not found. This might be okay for newer pywin32 versions.
)
echo.


echo Starting PyInstaller build for %AGENT_SCRIPT_NAME%...
REM Clean previous build artifacts
IF EXIST "dist" rmdir /s /q "dist"
IF EXIST "build" rmdir /s /q "build"
IF EXIST "%OUTPUT_EXE_NAME%.spec" del "%OUTPUT_EXE_NAME%.spec"
echo.

REM --- PyInstaller Command with Hidden Imports ---
pyinstaller --onefile --windowed --name %OUTPUT_EXE_NAME% ^
--clean ^
--log-level %PYINSTALLER_LOG_LEVEL% ^
--noconfirm ^
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
%AGENT_SCRIPT_NAME%

REM Check if build was successful
if %errorlevel% neq 0 (
    echo.
    echo *******************************************************
    echo ***               PYINSTALLER BUILD FAILED          ***
    echo *******************************************************
    echo Please check the output above for specific errors from PyInstaller.
    echo Common issues:
    echo   - Missing Python packages (check pip install steps).
    echo   - Incorrect paths or script names.
    echo   - Antivirus software interfering with PyInstaller.
    echo   - Problems with specific hidden imports if versions changed.
    pause
    exit /b %errorlevel%
)

echo.
echo *******************************************************
echo ***            PYINSTALLER BUILD SUCCESSFUL         ***
echo *******************************************************
echo Executable created: dist\%OUTPUT_EXE_NAME%.exe
echo.

REM Optional: Deactivate virtual environment if it was used and VIRTUAL_ENV is set
IF DEFINED VIRTUAL_ENV (
   echo Deactivating virtual environment (if one was active through this script)...
   REM 'call deactivate' might work if the venv sets it, otherwise no standard command.
   REM For 'venv' created by 'python -m venv', there's no direct deactivate.bat to call broadly.
   REM The user can close the cmd window or manually deactivate if needed.
)

echo Build process finished.
pause