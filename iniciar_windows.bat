@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 -m pip install -r requirements.txt
    py -3 main.py
) else (
    python -m pip install -r requirements.txt
    python main.py
)
pause