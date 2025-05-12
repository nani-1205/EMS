@echo off
echo Building Monitoring Agent EXE...

REM Ensure you are in the agent directory or adjust paths accordingly
REM Activate your Python virtual environment if you use one
REM Example: ..\venv\Scripts\activate

REM Install PyInstaller if not already installed
pip install pyinstaller

REM Install agent dependencies
pip install -r requirements.txt

REM --- PyInstaller Command ---
REM --onefile: Creates a single executable file
REM --noconsole OR --windowed: Prevents the console window from appearing (CRUCIAL for stealth)
REM --name: Specifies the name of the output executable
REM --icon: Optional: specify an icon file (.ico)
REM --add-data: If you need to bundle config files or other assets (use ; for separator on Windows)
REM            Example: --add-data "config.py;." to bundle config.py in the root of the exe's temp dir

pyinstaller --onefile --windowed --name monitoring_agent agent.py

REM Check if build was successful
if %errorlevel% neq 0 (
    echo Build failed!
    pause
    exit /b %errorlevel%
)

echo EXE created successfully in the 'dist' folder!

REM Optional: Clean up build files
REM rmdir /s /q build
REM del /q monitoring_agent.spec

pause