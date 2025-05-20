@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

echo ========================================================
echo == TekPossible Monitor Agent - PyInstaller Build Script ==
echo ========================================================
echo.

REM Get the directory of this batch script
SET "SCRIPT_DIR=%~dp0"
REM Navigate to the script's directory
echo Changing directory to: %SCRIPT_DIR%
cd /D "%SCRIPT_DIR%"
if errorlevel 1 (
    echo ERROR: Could not change directory to %SCRIPT_DIR%.
    pause
    exit /b 1
)

REM --- Configuration ---
SET VENV_NAME=venv
SET OUTPUT_EXE_NAME=monitoring_agent
SET AGENT_SCRIPT_NAME=agent.py
SET REQUIREMENTS_FILE=requirements.txt
SET PYINSTALLER_LOG_LEVEL=INFO
SET PYTHON_CMD=python

REM --- Virtual Environment Handling FIRST ---
SET VENV_PATH=%SCRIPT_DIR%%VENV_NAME%
IF EXIST "%VENV_PATH%\Scripts\activate.bat" (
    echo Virtual environment '%VENV_NAME%' found.
    echo Activating virtual environment...
    call "%VENV_PATH%\Scripts\activate.bat"
    if errorlevel 1 (
        echo WARNING: Failed to activate virtual environment '%VENV_NAME%'.
        echo Will attempt to use global 'python'.
        SET PYTHON_CMD=python
    ) ELSE (
        echo Virtual environment activated.
        IF DEFINED VIRTUAL_ENV (
            SET PYTHON_CMD="%VIRTUAL_ENV%\Scripts\python.exe"
            echo Using Python from VENV: !PYTHON_CMD!
        ) ELSE (
            echo VIRTUAL_ENV not set after activation. Using 'python'.
            SET PYTHON_CMD=python
        )
    )
) ELSE (
    echo No '%VENV_NAME%' virtual environment found. Attempting to use global 'python'.
    SET PYTHON_CMD=python
)
echo.

REM --- Check for Python (Bypassing the problematic IF for now) ---
echo Checking for Python installation using: %PYTHON_CMD%
%PYTHON_CMD% --version
SET PYTHON_CHECK_ERRORLEVEL=!errorlevel!
echo Python version command executed. Stored Errorlevel: !PYTHON_CHECK_ERRORLEVEL!
echo Assuming Python check is OK to proceed (Errorlevel was !PYTHON_CHECK_ERRORLEVEL!).
echo If Python version was not printed above, or errorlevel is not 0, there is an issue.
echo.

REM --- Check for Pip (Bypassing the problematic IF for now) ---
echo Checking for pip using: %PYTHON_CMD%
%PYTHON_CMD% -m pip --version
SET PIP_CHECK_ERRORLEVEL=!errorlevel!
echo Pip version command executed. Stored Errorlevel: !PIP_CHECK_ERRORLEVEL!
echo Assuming Pip check is OK to proceed (Errorlevel was !PIP_CHECK_ERRORLEVEL!).
echo If Pip version was not printed above, or errorlevel is not 0, there is an issue.
echo.

echo Upgrading pip in the current environment...
%PYTHON_CMD% -m pip install --upgrade pip
echo.

echo Installing/Updating core build dependencies (PyInstaller, pywin32, psutil)...
%PYTHON_CMD% -m pip install --upgrade pyinstaller pywin32 psutil
if !errorlevel! neq 0 (
    echo ERROR: Failed to install/update PyInstaller, pywin32, or psutil.
    pause
    exit /b 1
)
echo Core build dependencies installed/updated.
echo.

IF EXIST "%REQUIREMENTS_FILE%" (
    echo Installing agent dependencies from %REQUIREMENTS_FILE%...
    %PYTHON_CMD% -m pip install -r %REQUIREMENTS_FILE%
    if !errorlevel! neq 0 (
        echo ERROR: Failed to install agent dependencies from %REQUIREMENTS_FILE%.
        pause
        exit /b 1
    )
    echo Agent dependencies installed.
) ELSE (
    echo WARNING: %REQUIREMENTS_FILE% not found. Skipping agent dependency installation.
)
echo.

echo Running pywin32_postinstall script (if available)...
SET PYWIN32_POSTINSTALL_SCRIPT=
IF DEFINED VIRTUAL_ENV (
    IF EXIST "%VIRTUAL_ENV%\Scripts\pywin32_postinstall.py" (
        SET PYWIN32_POSTINSTALL_SCRIPT="%VIRTUAL_ENV%\Scripts\pywin32_postinstall.py"
    )
)
IF NOT DEFINED PYWIN32_POSTINSTALL_SCRIPT (
    FOR /F "delims=" %%G IN ('where pywin32_postinstall.py 2^>nul') DO (
        IF NOT DEFINED PYWIN32_POSTINSTALL_SCRIPT SET PYWIN32_POSTINSTALL_SCRIPT="%%G"
    )
)

IF DEFINED PYWIN32_POSTINSTALL_SCRIPT (
    echo Found pywin32_postinstall.py at !PYWIN32_POSTINSTALL_SCRIPT!
    %PYTHON_CMD% !PYWIN32_POSTINSTALL_SCRIPT! -install
    if !errorlevel! neq 0 (
        echo WARNING: pywin32_postinstall.py script execution might have failed.
    ) else (
        echo pywin32_postinstall.py executed.
    )
) ELSE (
     echo pywin32_postinstall.py script not found. This might be okay for newer pywin32 versions.
)
echo.

echo Starting PyInstaller build for %AGENT_SCRIPT_NAME%...
IF EXIST "dist" rmdir /s /q "dist"
IF EXIST "build" rmdir /s /q "build"
IF EXIST "%OUTPUT_EXE_NAME%.spec" del "%OUTPUT_EXE_NAME%.spec"
echo.

%PYTHON_CMD% -m PyInstaller --onefile --windowed --name %OUTPUT_EXE_NAME% ^
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

if !errorlevel! neq 0 (
    echo. & echo ******************** & echo *** BUILD FAILED *** & echo ********************
    echo Check the output above for specific PyInstaller errors.
    pause
    exit /b !errorlevel!
)

echo. & echo ************************ & echo *** BUILD SUCCESSFUL *** & echo ************************
echo EXE created in the 'dist' folder: dist\%OUTPUT_EXE_NAME%.exe
echo.

echo Build process finished.
pause
ENDLOCAL