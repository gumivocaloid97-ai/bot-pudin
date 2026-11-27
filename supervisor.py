"""Mantiene el bot andando: si se cae, lo vuelve a levantar solo."""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
BOT = BASE / "bot.py"
REGISTRO = BASE / "supervisor.log"

ESPERA = 15
FALLOS_MAXIMOS = 5


def anotar(texto: str) -> None:
    try:
        with REGISTRO.open("a", encoding="utf-8") as archivo:
            archivo.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {texto}\n")
    except OSError:
        pass


def main() -> None:
    fallos = 0
    anotar("arranca el supervisor")
    while True:
        inicio = time.time()
        codigo = subprocess.call([sys.executable, str(BOT)], cwd=str(BASE))
        segundos = int(time.time() - inicio)
        anotar(f"el bot termino con codigo {codigo} despues de {segundos}s")

        if (BASE / "detener.txt").exists():
            (BASE / "detener.txt").unlink()
            anotar("apagado a pedido")
            return

        fallos = fallos + 1 if segundos < 60 else 0
        if fallos >= FALLOS_MAXIMOS:
            anotar(f"se cayo {FALLOS_MAXIMOS} veces seguidas, lo dejo apagado. Mira bot.log")
            return
        time.sleep(ESPERA)


if __name__ == "__main__":
    main()
