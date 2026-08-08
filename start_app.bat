@echo off
REM Inicia o Video Learning Tracker (auto_curso) - app web local
REM Uso: start_app.bat  (duplo clique ou no cmd/PowerShell)
REM Abre automaticamente http://127.0.0.1:8765 no navegador

setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_DIR=%CD%\.venv"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    if exist "%CD%\venv\Scripts\python.exe" (
        set "VENV_DIR=%CD%\venv"
    ) else (
        echo Criando ambiente virtual em .venv ...
        py -3 -m venv "%CD%\.venv" 2>nul || python -m venv "%CD%\.venv"
        if errorlevel 1 (
            echo Erro ao criar o ambiente virtual. Instale Python 3.11+.
            exit /b 1
        )
        set "VENV_DIR=%CD%\.venv"
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo Nao foi possivel ativar o ambiente virtual em: %VENV_DIR%
    exit /b 1
)

python -m pip install -q --upgrade pip
pip install -q -e .
if errorlevel 1 (
    echo Erro ao instalar dependencias.
    exit /b 1
)

python -m auto_curso
exit /b %ERRORLEVEL%
