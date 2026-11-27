"""Arranque automatico con Windows y control del bot en segundo plano."""

from __future__ import annotations

import os
import subprocess
import sys
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


def arrancar() -> None:
    if not SUPERVISOR.exists():
        print("  Falta supervisor.py en la carpeta.")
        return
    subprocess.Popen(
        [str(python_oculto()), str(SUPERVISOR)],
        cwd=str(BASE),
        creationflags=SIN_VENTANA,
    )
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
