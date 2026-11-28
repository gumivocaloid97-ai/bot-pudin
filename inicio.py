"""Arranque automatico con Windows y control del bot en segundo plano."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
SUPERVISOR = BASE / "supervisor.py"
NOMBRE = "Bot Pudin.vbs"
SIN_VENTANA = 0x08000000


def python_oculto() -> Path:
    for nombre in ("pythonw.exe", "python.exe"):
        ruta = BASE / "runtime" / nombre
        if ruta.exists():
            return ruta
    return Path(sys.executable)


def carpeta_inicio() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SystemExit("No encuentro la carpeta APPDATA.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def contenido() -> str:
    return (
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.CurrentDirectory = "{BASE}"\r\n'
        f'sh.Run """{python_oculto()}"" ""{SUPERVISOR}""", 0, False\r\n'
    )


def instalar() -> None:
    destino = carpeta_inicio() / NOMBRE
    destino.write_text(contenido(), encoding="utf-8")
    print("  LISTO: el bot va a arrancar solo cuando prendas la PC.")
    print(f"  Archivo: {destino}")
    print("  Para arrancarlo ahora, sin reiniciar: Arrancar Bot.bat")


def quitar() -> None:
    destino = carpeta_inicio() / NOMBRE
    if destino.exists():
        destino.unlink()
        print("  LISTO: ya no arranca solo.")
    else:
        print("  No estaba instalado.")


MARCA = BASE / "arrancando.txt"
VALE_MARCA = 120


def _marca_vieja() -> bool:
    try:
        return time.time() - MARCA.stat().st_mtime > VALE_MARCA
    except OSError:
        return False


def _tomar_marca() -> bool:
    """Solo un arranque a la vez, aunque se hagan varios clics seguidos."""
    for _ in range(2):
        try:
            with open(MARCA, "x", encoding="utf-8") as archivo:
                archivo.write(str(int(time.time())))
            return True
        except FileExistsError:
            intacta = not _marca_vieja()
            try:
                rota = MARCA.stat().st_size == 0
            except OSError:
                rota = True
            if intacta and not rota:
                return False
            MARCA.unlink(missing_ok=True)
        except OSError:
            return False
    return False


def ocupado(puerto: int) -> bool:
    """True si algo ya esta escuchando en ese puerto de esta PC."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=0.4):
            return True
    except OSError:
        return False


def arrancar() -> None:
    if not SUPERVISOR.exists():
        print("  Falta supervisor.py en la carpeta.")
        return
    (BASE / "detener.txt").unlink(missing_ok=True)
    if ocupado(47777) or ocupado(47778):
        print("  Ya hay un Bot Pudin andando. No arranco otro.")
        return
    if not _tomar_marca():
        print("  Ya hay un arranque en curso. Espera unos segundos.")
        return
    try:
        subprocess.Popen(
            [str(python_oculto()), str(SUPERVISOR)],
            cwd=str(BASE),
            creationflags=SIN_VENTANA,
        )
    except (OSError, ValueError) as error:
        MARCA.unlink(missing_ok=True)
        print(f"  No pude arrancarlo: {error}")
        return
    print("  Bot arrancado en segundo plano.")


def estado() -> None:
    destino = carpeta_inicio() / NOMBRE
    print("  Arranque automatico:", "SI" if destino.exists() else "NO")
    print("  Python oculto:     ", python_oculto())
    print("  Supervisor:        ", "OK" if SUPERVISOR.exists() else "FALTA")
    print("  Registro:          ", "SI" if (BASE / "bot.log").exists() else "todavia no")


if __name__ == "__main__":
    orden = sys.argv[1] if len(sys.argv) > 1 else "estado"
    {"instalar": instalar, "quitar": quitar, "arrancar": arrancar}.get(orden, estado)()
