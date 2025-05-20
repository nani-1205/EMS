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
SET PYTHON_CMD_TEST=python

REM --- Virtual Environment Handling FIRST ---
SET VENV_PATH=%SCRIPT_DIR%%VENV_NAME%
IF EXIST "%VENV_PATH%\Scripts\activate.bat" (
    echo Virtual environment '%VENV_NAME%' found.
    echo Activating virtual environment...
    call "%VENV_PATH%\Scripts\activate.bat"
    if errorlevel 1 (
        echo WARNING: Failed to activate virtual environment '%VENV_NAME%'.
        echo Will attempt to use global 'python'.
        SET PYTHON_CMD_TEST=python
    ) ELSE (
        echo Virtual environment activated.
        IF DEFINED VIRTUAL_ENV (
            SET PYTHON_CMD_TEST="%VIRTUAL_ENV%\Scripts\python.exe"
            echo Using Python from VENV for test: !PYTHON_CMD_TEST!
        ) ELSE (
            echo VIRTUAL_ENV not set after activation. Using 'python' for test.
            SET PYTHON_CMD_TEST=python
        )
    )
) ELSE (
    echo No '%VENV_NAME%' virtual environment found. Attempting to use global 'python' for test.
    SET PYTHON_CMD_TEST=python
)
echo.

REM --- DIRECT PYTHON EXECUTION TEST ---
echo.
echo +++++++++++++++++++++++++++++++++++++++++++++++++++++++
echo +++          DIRECT PYTHON EXECUTION TEST           +++
echo +++++++++++++++++++++++++++++++++++++++++++++++++++++++
echo Will attempt to execute: !PYTHON_CMD_TEST! --version
echo.

!PYTHON_CMD_TEST! --version

echo.
echo Errorlevel immediately after direct execution: !errorlevel!
echo.
echo Now attempting the IF condition based on that errorlevel...

IF !errorlevel! NEQ 0 (
    echo   IF CONDITION: Python command failed with errorlevel !errorlevel!.
) ELSE (
    echo   IF CONDITION: Python command succeeded with errorlevel !errorlevel!.
)
echo +++++++++++++++++++++++++++++++++++++++++++++++++++++++
echo.

pause
echo Script will now exit for focused debugging of the above test.
exit /b 0

REM The rest of the script is temporarily bypassed for this test.
REM --- Check for Python and Pip (NOW uses %PYTHON_CMD%) ---
REM ... (rest of the script as before) ...