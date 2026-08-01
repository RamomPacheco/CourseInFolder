#!/usr/bin/env bash
# Inicia o Video Learning Tracker (auto_curso)
# Uso: ./start_app.sh

set -e
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv nao encontrado no PATH."
    echo "Instale em: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

uv sync
uv run python -m auto_curso
