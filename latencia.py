"""Mide cuanto se atrasa el bucle de eventos.

Si el numero sube, algo esta bloqueando al bot (una consulta lenta, un
archivo grande, una llamada de red sin await).
"""

from __future__ import annotations

import asyncio
import time

_ultimo = 0.0
_peor = 0.0


def ultimo() -> float:
    """Atraso del ultimo control, en milisegundos."""
    return _ultimo


def peor() -> float:
    """El peor atraso desde que arranco el bot."""
    return _peor


async def vigilar(cada: float = 5.0) -> None:
    global _ultimo, _peor
    while True:
        arranque = time.perf_counter()
        await asyncio.sleep(cada)
        atraso = (time.perf_counter() - arranque - cada) * 1000
        _ultimo = max(0.0, atraso)
        if _ultimo > _peor:
            _peor = _ultimo
