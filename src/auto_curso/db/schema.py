from __future__ import annotations

from auto_curso.db.connection import get_connection


def initialize_database() -> None:
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
        """)
