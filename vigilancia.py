"""Auto-moderacion basica: invitaciones, estafas y spam."""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque

import discord

INVITACION = re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite|discord\.me)/[\w-]+", re.I)

SENALES_ESTAFA = (
    "free nitro",
    "nitro gratis",
    "nitro free",
    "regalo de steam",
    "steamcommunity.com/gift",
    "ganaste un",
    "ganaste una",
    "claim your prize",
    "free robux",
    "duplicamos tus",
)

# canales donde no se filtra nada (ahi se comparten pruebas y links)
SIN_FILTRO = ("reportes", "staff", "registro")

LIMITE_SPAM = 5
VENTANA_SPAM = 8.0


def es_staff(miembro: discord.Member) -> bool:
    permisos = getattr(miembro, "guild_permissions", None)
    return bool(permisos and (permisos.administrator or permisos.manage_messages))


def motivo_bloqueo(texto: str) -> str | None:
    if INVITACION.search(texto):
        return "invitacion a otro servidor"
    bajo = texto.lower()
    if any(senal in bajo for senal in SENALES_ESTAFA):
        return "posible estafa"
    return None


def canal_sin_filtro(nombre: str) -> bool:
    bajo = (nombre or "").lower()
    return any(clave in bajo for clave in SIN_FILTRO)


class AntiSpam:
    """Cuenta cuantos mensajes manda cada persona en una ventana de segundos."""

    def __init__(self, limite: int = LIMITE_SPAM, ventana: float = VENTANA_SPAM) -> None:
        self.limite = limite
        self.ventana = ventana
        self._marcas: dict[int, deque[float]] = defaultdict(deque)

    def es_spam(self, autor_id: int) -> bool:
        ahora = time.monotonic()
        marcas = self._marcas[autor_id]
        marcas.append(ahora)
        while marcas and ahora - marcas[0] > self.ventana:
            marcas.popleft()
        return len(marcas) >= self.limite
