@echo off
cd /d "%~dp0"
where python >nul 2>&1
if %errorlevel%==0 (
    python main.py
    set RUN_EXIT=%errorlevel%
    goto done
)
where py >nul 2>&1
if %errorlevel%==0 (
    py main.py
    set RUN_EXIT=%errorlevel%
    goto done
)
echo Python not found on PATH.
pause
exit /b 1

:done
if not "%RUN_EXIT%"=="0" pause
