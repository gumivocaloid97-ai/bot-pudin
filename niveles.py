"""Persistencia y matemática del sistema de niveles."""

import os
import sqlite3
import time
from pathlib import Path

# En un host con disco persistente conviene apuntar DB_PATH a la ruta montada.
RUTA_DB = Path(os.environ.get("DB_PATH") or Path(__file__).with_name("niveles.db"))

# Los niveles anteriores a separar por servidor pertenecen a este.
GUILD_ORIGINAL = 1575699459680112721


def conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(RUTA_DB, check_same_thread=False)
    columnas = [c[1] for c in conn.execute("PRAGMA table_info(niveles)")]
    migrar = bool(columnas) and "guild_id" not in columnas
    if migrar:
        conn.execute("ALTER TABLE niveles RENAME TO niveles_viejo")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS niveles (
            guild_id   INTEGER NOT NULL,
            user_id    INTEGER NOT NULL,
            xp         INTEGER NOT NULL DEFAULT 0,
            nivel      INTEGER NOT NULL DEFAULT 0,
            ultimo_msg INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )"""
    )
    if migrar:
        conn.execute(
            "INSERT OR IGNORE INTO niveles (guild_id, user_id, xp, nivel, ultimo_msg) "
            "SELECT ?, user_id, xp, nivel, ultimo_msg FROM niveles_viejo",
            (GUILD_ORIGINAL,),
        )
        conn.execute("DROP TABLE niveles_viejo")
    conn.commit()
    return conn


def reclamar_bienvenida(
    conn: sqlite3.Connection, guild_id: int, user_id: int, segundos: int = 120
) -> bool:
    """True solo la primera vez: evita saludar dos veces al mismo miembro."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS bienvenidas (
            guild_id INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            ts       REAL    NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )"""
    )
    ahora = time.time()
    fila = conn.execute(
        "SELECT ts FROM bienvenidas WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    if fila is not None and ahora - fila[0] < segundos:
        return False
    conn.execute(
        "INSERT OR REPLACE INTO bienvenidas (guild_id, user_id, ts) VALUES (?, ?, ?)",
        (guild_id, user_id, ahora),
    )
    conn.commit()
    return True


def xp_para_nivel(nivel: int) -> int:
    """XP necesario para pasar del nivel indicado al siguiente."""
    return 5 * nivel * nivel + 50 * nivel + 100


def nivel_desde_xp(xp: int) -> tuple[int, int]:
    """Devuelve (nivel, xp dentro del nivel actual)."""
    nivel = 0
    while xp >= xp_para_nivel(nivel):
        xp -= xp_para_nivel(nivel)
        nivel += 1
    return nivel, xp


def fila(conn: sqlite3.Connection, guild_id: int, user_id: int) -> tuple[int, int]:
    datos = conn.execute(
        "SELECT xp, nivel FROM niveles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    return datos if datos else (0, 0)


def sumar_xp(
    conn: sqlite3.Connection, guild_id: int, user_id: int, cantidad: int
) -> tuple[int, int, int]:
    """Suma XP y devuelve (nivel_anterior, nivel_nuevo, xp_total)."""
    xp_total, nivel_anterior = fila(conn, guild_id, user_id)
    xp_total += cantidad
    nivel_nuevo, _ = nivel_desde_xp(xp_total)
    conn.execute(
        "INSERT INTO niveles (guild_id, user_id, xp, nivel) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = excluded.xp, nivel = excluded.nivel",
        (guild_id, user_id, xp_total, nivel_nuevo),
    )
    conn.commit()
    return nivel_anterior, nivel_nuevo, xp_total


def puede_ganar_por_mensaje(
    conn: sqlite3.Connection, guild_id: int, user_id: int, enfriamiento: int
) -> bool:
    ahora = int(time.time())
    datos = conn.execute(
        "SELECT ultimo_msg FROM niveles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    ultimo = datos[0] if datos else 0
    if ahora - ultimo < enfriamiento:
        return False
    conn.execute(
        "INSERT INTO niveles (guild_id, user_id, ultimo_msg) VALUES (?, ?, ?) "
        "ON CONFLICT(guild_id, user_id) DO UPDATE SET ultimo_msg = excluded.ultimo_msg",
        (guild_id, user_id, ahora),
    )
    conn.commit()
    return True


def ranking(
    conn: sqlite3.Connection, guild_id: int, limite: int = 10
) -> list[tuple[int, int, int]]:
    return conn.execute(
        "SELECT user_id, xp, nivel FROM niveles WHERE guild_id = ? ORDER BY xp DESC LIMIT ?",
        (guild_id, limite),
    ).fetchall()


def puesto(conn: sqlite3.Connection, guild_id: int, user_id: int) -> int | None:
    (xp, _) = fila(conn, guild_id, user_id)
    if xp == 0:
        return None
    (cantidad,) = conn.execute(
        "SELECT COUNT(*) FROM niveles WHERE guild_id = ? AND xp > ?", (guild_id, xp)
    ).fetchone()
    return cantidad + 1
