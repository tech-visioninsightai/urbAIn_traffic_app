@echo off

setlocal EnableExtensions



REM Vision Insight AI - urbAIn - traffic (aplicacion de escritorio nativa)

set "APP_DIR=%~dp0"

set "ROOT_DIR=%APP_DIR%.."

cd /d "%ROOT_DIR%" || (

    echo No se pudo entrar en: %ROOT_DIR%

    pause

    exit /b 1

)



where python >nul 2>&1

if errorlevel 1 (

    echo Python no esta en el PATH. Instala Python 3.10+ y vuelve a intentar.

    pause

    exit /b 1

)



if exist "%ROOT_DIR%\.venv\Scripts\activate.bat" (

    call "%ROOT_DIR%\.venv\Scripts\activate.bat"

)



python -c "import fastapi, uvicorn, webview" >nul 2>&1

if errorlevel 1 (

    echo Instalando dependencias de urbAIn_traffic_app...

    python -m pip install -r "%APP_DIR%requirements.txt"

    if errorlevel 1 (

        echo Fallo pip install.

        pause

        exit /b 1

    )

)



echo Iniciando Vision Insight AI - urbAIn - traffic...

echo.



python -m urbAIn_traffic_app

set EXITCODE=%ERRORLEVEL%



if %EXITCODE% neq 0 (

    echo.

    echo La app termino con error %EXITCODE%.

    echo Si la ventana no abre, instala WebView2 Runtime:

    echo https://go.microsoft.com/fwlink/p/?LinkId=2124703

    pause

)



endlocal

exit /b %EXITCODE%

