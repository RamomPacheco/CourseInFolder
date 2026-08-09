from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from auto_curso.constants import get_database_path


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Abre uma conexão SQLite de curta duração, com commit/rollback automáticos.

    Cada chamada abre e fecha sua própria conexão (não há pool) — modelo
    simples e seguro para um app local de um único usuário. `PRAGMA
    foreign_keys = ON` é ativado em toda conexão para que as cascatas
    de exclusão (ON DELETE CASCADE) entre Courses/Videos/notas/materiais
    realmente funcionem.

    Yields:
        sqlite3.Connection: Conexão com `row_factory = sqlite3.Row`
            (permite acessar colunas por índice ou por nome).

    Raises:
        Exception: Qualquer exceção levantada dentro do bloco `with` é
            propagada após um rollback; sem exceção, a transação é commitada.
    """
    conn = sqlite3.connect(get_database_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
