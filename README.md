# Video Learning Tracker (Python)

Aplicativo desktop para acompanhar o progresso de estudos em pastas de vídeo. Cada pasta é um **curso**; o app salva onde você parou e retoma na mesma posição.

## Requisitos

- Python 3.11+
- PySide6 (reprodutor multimídia nativo do Qt — áudio e vídeo)

## Instalação

```bash
cd auto_curso
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Executar

```bash
python -m auto_curso
```

## Uso

1. Clique em **+ Adicionar curso** e escolha uma pasta com vídeos.
2. Dê duplo clique em um vídeo para reproduzir (retoma de onde parou).
3. Use os filtros: Todos / Pendentes / Concluídos.
4. **Atualizar** reescaneia a pasta (novos arquivos entram; removidos saem).
5. **Tela cheia** no player ou tecla **F11**.

## Atalhos

| Tecla | Ação |
|-------|------|
| Espaço | Play / Pause |
| ← | Voltar 10 s |
| → | Avançar 10 s |
| F11 | Tela cheia |

## Extensões suportadas

`.mp4`, `.mkv`, `.avi`, `.webm`, `.mov`, `.wmv`, `.m4v`, `.flv`, `.mpeg`, `.mpg`, `.3gp`, `.ogv`

## Dados locais

- Windows: `%APPDATA%\auto_curso\data.db`
- Linux/macOS: `~/.local/share/auto_curso/data.db`

## Conclusão automática

Vídeo marcado como concluído ao atingir **95%** da duração.

## Tecnologia

- **UI:** PySide6
- **Player:** QMediaPlayer + QVideoWidget (multimídia nativa)
- **Banco:** SQLite
