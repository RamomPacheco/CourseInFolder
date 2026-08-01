@echo off
REM Inicia o Video Learning Tracker (auto_curso)
REM Uso: start_app.bat  (duplo clique ou no cmd/PowerShell)

setlocal EnableExtensions
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv nao encontrado no PATH.
    echo Instale em: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

uv sync
if errorlevel 1 (
    echo Erro ao instalar dependencias com uv.
    exit /b 1
)

uv run python -m auto_curso
exit /b %ERRORLEVEL%
