@echo off
setlocal EnableExtensions

REM Vision Insight AI - urbAIn - traffic
set "APP_DIR=%~dp0"
set "ROOT_DIR=%APP_DIR%.."
cd /d "%ROOT_DIR%"

if exist "%ROOT_DIR%\.venv\Scripts\activate.bat" (
    call "%ROOT_DIR%\.venv\Scripts\activate.bat"
)

python -m urbAIn_traffic_app
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% neq 0 (
    echo.
    echo La app termino con error %EXITCODE%.
    pause
)

endlocal
exit /b %EXITCODE%
