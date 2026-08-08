# Video Learning Tracker (Python)

Aplicativo web local para acompanhar o progresso de estudos em pastas de vídeo. Cada pasta é um **curso**; o app salva onde você parou e retoma na mesma posição. Roda 100% na sua máquina: um servidor FastAPI local serve a interface web e os vídeos direto do seu disco.

## Requisitos

- Python 3.11+

## Instalação

```bash
uv sync
```

(ou `pip install -e .` num virtualenv)

## Executar

```bash
uv run auto-curso-web
```

Abre automaticamente `http://127.0.0.1:8765` no navegador padrão.

## Uso

1. Clique em **Adicionar curso** e navegue até a pasta com os vídeos.
2. Clique num vídeo na lista para reproduzir (retoma de onde parou).
3. Use os filtros: Todos / Pendentes / Concluídos.
4. **Atualizar** reescaneia a pasta (novos arquivos entram; removidos saem).
5. Marque/desmarque manualmente a caixa de concluído em qualquer vídeo.

## Extensões suportadas

`.mp4`, `.mkv`, `.avi`, `.webm`, `.mov`, `.wmv`, `.m4v`, `.flv`, `.mpeg`, `.mpg`, `.3gp`, `.ogv`

## Dados locais

- Windows: `%APPDATA%\auto_curso\data.db`
- Linux/macOS: `~/.local/share/auto_curso/data.db`

## Conclusão automática

Vídeo marcado como concluído ao atingir **95%** da duração.

## Tecnologia

- **Backend:** FastAPI + Uvicorn (rodando localmente, sem exposição externa)
- **Player:** tag `<video>` nativa do navegador, streaming com suporte a `Range` (permite avançar/retroceder)
- **Frontend:** HTML/CSS/JS estáticos (sem build step), design system "Nocturne" (o mesmo do protótipo `CourseVault.dc.html`)
- **Banco:** SQLite
