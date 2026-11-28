"""Mantiene el bot andando: si se cae, lo vuelve a levantar solo."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
BOT = BASE / "bot.py"
REGISTRO = BASE / "supervisor.log"

ESPERA = 15
ESPERA_REINICIO = 3
FALLOS_MAXIMOS = 5
PUERTO_BOT = 47777
PUERTO_CANDADO = 47778
VALE_REINICIO = 90
MIRAR_CADA = 3

_CANDADO = None


def anotar(texto: str) -> None:
    try:
        with REGISTRO.open("a", encoding="utf-8") as archivo:
            archivo.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {texto}\n")
    except OSError:
        pass


def ocupado(puerto: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            return s.connect_ex(("127.0.0.1", puerto)) == 0
    except OSError:
        return False


def unico() -> bool:
    """Un solo supervisor por PC: si ya hay otro, este se va."""
    global _CANDADO
    try:
        _CANDADO = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _CANDADO.bind(("127.0.0.1", PUERTO_CANDADO))
        _CANDADO.listen(1)
        return True
    except OSError:
        if _CANDADO is not None:
            _CANDADO.close()
            _CANDADO = None
        return False


def reinicio_pedido() -> bool:
    """True si el bot pidio reiniciarse hace poco (y borra la nota)."""
    marca = BASE / "reinicio.txt"
    try:
        edad = time.time() - marca.stat().st_mtime
    except OSError:
        return False
    marca.unlink(missing_ok=True)
    return edad <= VALE_REINICIO


def apagado_pedido() -> bool:
    return (BASE / "detener.txt").exists()


def esperar(segundos: float) -> None:
    """Espera mirando si pidieron apagar, para no dormirse de mas."""
    fin = time.time() + segundos
    while time.time() < fin:
        if apagado_pedido():
            return
        time.sleep(0.4)


def main() -> None:
    if not unico():
        anotar("ya hay un supervisor andando, este no arranca")
        return

    (BASE / "arrancando.txt").unlink(missing_ok=True)

    fallos = 0
    anotar("arranca el supervisor")
    while True:
        if apagado_pedido():
            anotar("apagado a pedido (la nota queda hasta que lo prendan)")
            return

        if ocupado(PUERTO_BOT):
            # Hay un bot andando que no es hijo mio (un reinicio con execv, o una
            # copia abierta a mano). Lo vigilo pero NO lanzo otro.
            time.sleep(MIRAR_CADA)
            continue

        inicio = time.time()
        codigo = subprocess.call([sys.executable, str(BOT)], cwd=str(BASE))
        segundos = int(time.time() - inicio)
        anotar(f"el bot termino con codigo {codigo} despues de {segundos}s")

        if apagado_pedido():
            anotar("apagado a pedido (la nota queda hasta que lo prendan)")
            return

        if reinicio_pedido():
            anotar("reinicio pedido: espero que vuelva y no lanzo otro")
            fallos = 0
            esperar(ESPERA_REINICIO)
            continue

        fallos = fallos + 1 if segundos < 60 else 0
        if fallos >= FALLOS_MAXIMOS:
            anotar(f"se cayo {FALLOS_MAXIMOS} veces seguidas, lo dejo apagado. Mira bot.log")
            return
        esperar(ESPERA)


if __name__ == "__main__":
    main()
