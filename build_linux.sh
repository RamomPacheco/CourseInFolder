#!/usr/bin/env bash
# Gera o executavel Linux (dist/auto-curso) via PyInstaller.
set -euo pipefail
cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
    uv sync
    uv run pyinstaller auto_curso.spec --noconfirm
else
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -e . pyinstaller
    pyinstaller auto_curso.spec --noconfirm
fi

echo
echo "Executavel gerado em: dist/auto-curso"
