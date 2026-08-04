@echo off
REM Gera o executavel Windows (dist\auto-curso.exe) via PyInstaller.
REM Rodar em uma maquina Windows com Python 3.11+ instalado.
REM Uso: build_windows.bat  (duplo clique ou no cmd/PowerShell)

setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_DIR=%CD%\.venv"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Criando ambiente virtual em .venv ...
    py -3 -m venv "%CD%\.venv" 2>nul || python -m venv "%CD%\.venv"
    if errorlevel 1 (
        echo Erro ao criar o ambiente virtual. Instale Python 3.11+.
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo Nao foi possivel ativar o ambiente virtual em: %VENV_DIR%
    exit /b 1
)

python -m pip install -q --upgrade pip
pip install -q -e .
pip install -q pyinstaller
if errorlevel 1 (
    echo Erro ao instalar dependencias.
    exit /b 1
)

pyinstaller auto_curso.spec --noconfirm
if errorlevel 1 (
    echo Erro ao gerar o executavel.
    exit /b 1
)

echo.
echo Executavel gerado em: dist\auto-curso.exe
exit /b 0
