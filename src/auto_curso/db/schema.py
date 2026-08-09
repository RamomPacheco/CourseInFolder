from __future__ import annotations

import sqlite3

from auto_curso.db.connection import get_connection

# (table, column, column definition) — added via ALTER TABLE for DBs created
# before these columns existed. CREATE TABLE IF NOT EXISTS alone does not
# retrofit new columns onto an already-existing table.
_MIGRATIONS: list[tuple[str, str, str]] = [
    ("Courses", "DeletedAt", "TEXT NULL"),
    ("Courses", "Description", "TEXT NULL"),
    ("Courses", "CoverStoredName", "TEXT NULL"),
    ("Videos", "DeletedAt", "TEXT NULL"),
    ("Videos", "IsManual", "INTEGER NOT NULL DEFAULT 0"),
    ("Videos", "ManualStoredName", "TEXT NULL"),
    ("Videos", "DisplayTitle", "TEXT NULL"),
    ("VideoNotes", "DeletedAt", "TEXT NULL"),
    ("VideoMaterials", "DeletedAt", "TEXT NULL"),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Aplica, de forma idempotente, as colunas novas ainda ausentes em bancos já existentes.

    `CREATE TABLE IF NOT EXISTS` não retrofita colunas em uma tabela
    que já existe, então cada entrada de `_MIGRATIONS` é conferida via
    `PRAGMA table_info` antes de rodar o `ALTER TABLE ADD COLUMN`
    correspondente — seguro para chamar repetidamente e não apaga
    nenhum dado existente.

    Args:
        conn (sqlite3.Connection): Conexão aberta a usar para as migrações.
    """
    for table, column, definition in _MIGRATIONS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_database() -> None:
    """Cria as tabelas do banco (se necessário) e aplica migrações pendentes.

    Chamado no startup do servidor (ver `web.server.lifespan`) e
    também em `main()`, como rede de segurança para quem rodar o
    módulo diretamente. Seguro para chamar múltiplas vezes.
    """
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS Courses (
                Id TEXT PRIMARY KEY,
                Name TEXT NOT NULL,
                FolderPath TEXT NOT NULL UNIQUE,
                AddedAt TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS Videos (
                Id TEXT PRIMARY KEY,
                CourseId TEXT NOT NULL,
                RelativePath TEXT NOT NULL,
                FileName TEXT NOT NULL,
                SortOrder INTEGER NOT NULL,
                FileSizeBytes INTEGER NOT NULL,
                DurationSeconds REAL NULL,
                FOREIGN KEY (CourseId) REFERENCES Courses(Id) ON DELETE CASCADE,
                UNIQUE (CourseId, RelativePath)
            );

            CREATE TABLE IF NOT EXISTS PlaybackProgress (
                VideoId TEXT PRIMARY KEY,
                PositionSeconds REAL NOT NULL,
                IsCompleted INTEGER NOT NULL,
                WatchedPercent REAL NOT NULL,
                LastWatchedAt TEXT NOT NULL,
                FOREIGN KEY (VideoId) REFERENCES Videos(Id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS IX_Videos_CourseId ON Videos(CourseId);

            CREATE TABLE IF NOT EXISTS VideoNotes (
                Id TEXT PRIMARY KEY,
                VideoId TEXT NOT NULL,
                TimeSeconds REAL NOT NULL,
                Text TEXT NOT NULL,
                CreatedAt TEXT NOT NULL,
                FOREIGN KEY (VideoId) REFERENCES Videos(Id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS IX_VideoNotes_VideoId ON VideoNotes(VideoId);

            CREATE TABLE IF NOT EXISTS CourseNotes (
                CourseId TEXT PRIMARY KEY,
                Text TEXT NOT NULL,
                FOREIGN KEY (CourseId) REFERENCES Courses(Id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS VideoFavorites (
                VideoId TEXT PRIMARY KEY,
                FOREIGN KEY (VideoId) REFERENCES Videos(Id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS VideoMaterials (
                Id TEXT PRIMARY KEY,
                VideoId TEXT NOT NULL,
                FileName TEXT NOT NULL,
                StoredName TEXT NOT NULL,
                MimeType TEXT NOT NULL,
                SizeBytes INTEGER NOT NULL,
                UploadedAt TEXT NOT NULL,
                FOREIGN KEY (VideoId) REFERENCES Videos(Id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS IX_VideoMaterials_VideoId ON VideoMaterials(VideoId);

            CREATE TABLE IF NOT EXISTS ExcludedVideoPaths (
                CourseId TEXT NOT NULL,
                RelativePath TEXT NOT NULL,
                PRIMARY KEY (CourseId, RelativePath)
            );
        """)
        _apply_migrations(conn)
