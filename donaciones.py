"""Donadores con vencimiento: un mes y se renueva o se cae."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

ARCHIVO = Path(__file__).with_name("donadores.db")
DIAS_POR_DEFECTO = 30
DIAS_DE_AVISO = 3


def conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(ARCHIVO)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS donadores (
            guild_id INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            vence    REAL    NOT NULL,
            avisado  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pagos (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            dias     INTEGER NOT NULL,
            fecha    REAL    NOT NULL,
            quien    INTEGER
        )
        """
    )
    conn.commit()
    return conn


def otorgar(
    conn: sqlite3.Connection,
    guild_id: int,
    user_id: int,
    dias: int = DIAS_POR_DEFECTO,
    quien: int | None = None,
) -> float:
    """Suma dias desde hoy, o desde el vencimiento si todavia le queda."""
    ahora = time.time()
    actual = vence(conn, guild_id, user_id)
    base = actual if actual and actual > ahora else ahora
    nuevo = base + dias * 86400
    conn.execute(
        """
        INSERT INTO donadores (guild_id, user_id, vence, avisado)
        VALUES (?, ?, ?, 0)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET vence = ?, avisado = 0
        """,
        (guild_id, user_id, nuevo, nuevo),
    )
    conn.execute(
        "INSERT INTO pagos (guild_id, user_id, dias, fecha, quien) VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, dias, time.time(), quien),
    )
    conn.commit()
    return nuevo


def vence(conn: sqlite3.Connection, guild_id: int, user_id: int) -> float | None:
    fila = conn.execute(
        "SELECT vence FROM donadores WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    return fila[0] if fila else None


def listar(conn: sqlite3.Connection, guild_id: int) -> list[tuple[int, float, int]]:
    return conn.execute(
        "SELECT user_id, vence, avisado FROM donadores WHERE guild_id = ? ORDER BY vence",
        (guild_id,),
    ).fetchall()


def marcar_avisado(conn: sqlite3.Connection, guild_id: int, user_id: int) -> None:
    conn.execute(
        "UPDATE donadores SET avisado = 1 WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    conn.commit()


def quitar(conn: sqlite3.Connection, guild_id: int, user_id: int) -> None:
    conn.execute(
        "DELETE FROM donadores WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    conn.commit()


def pagos_de(conn: sqlite3.Connection, guild_id: int, user_id: int) -> list[tuple[int, float]]:
    return conn.execute(
        "SELECT dias, fecha FROM pagos WHERE guild_id = ? AND user_id = ? ORDER BY fecha",
        (guild_id, user_id),
    ).fetchall()


def resumen(conn: sqlite3.Connection, guild_id: int) -> list[tuple[int, int, int, float]]:
    """(user_id, dias_totales, cantidad_de_pagos, ultimo_pago)"""
    return conn.execute(
        """
        SELECT user_id, SUM(dias), COUNT(*), MAX(fecha)
        FROM pagos WHERE guild_id = ?
        GROUP BY user_id ORDER BY SUM(dias) DESC
        """,
        (guild_id,),
    ).fetchall()


def dias_restantes(vence_en: float) -> int:
    return max(0, int((vence_en - time.time()) // 86400))
