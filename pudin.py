"""El programa del bot: una sola cosa que abre la ventana y arranca todo.

Se encarga de que el bot este andando y de que la ventana pueda abrirse.
Si algo falla, lo deja anotado en panel.log y avisa con un cartel.
"""

from __future__ import annotations

import os
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
REGISTRO = CARPETA / "panel.log"
API = "http://127.0.0.1:8777"


def anotar(texto: str) -> None:
    try:
        with REGISTRO.open("a", encoding="utf-8") as archivo:
            archivo.write(time.strftime("%d/%m %H:%M:%S ") + texto.rstrip() + "\n")
    except OSError:
        pass


def cartel(titulo: str, mensaje: str) -> None:
    anotar(f"{titulo}: {mensaje}")
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, mensaje, titulo, 0x30)
    except Exception:
        print(f"{titulo}: {mensaje}")


def bot_anda() -> bool:
    try:
        with urllib.request.urlopen(API + "/api/estado", timeout=1.0) as respuesta:
            return respuesta.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def main() -> None:
    anotar("--- abriendo el bot ---")

    try:
        import actualizar

        actualizar.asegurar_paquetes()
        actualizar.asegurar_tkinter()
    except Exception:
        anotar(traceback.format_exc())

    if not bot_anda():
        anotar("estaba apagado, lo arranco")
        try:
            import inicio

            inicio.arrancar()
            os.environ["PUDIN_ARRANCANDO"] = "1"
        except Exception:
            anotar(traceback.format_exc())

    try:
        import app

        app.main()
    except Exception:
        anotar(traceback.format_exc())
        cartel(
            "Bot Pudin",
            "No pude abrir la ventana del bot.\n\n"
            "El detalle quedo en panel.log.\n"
            "Mientras tanto el panel funciona en el navegador.",
        )
        try:
            import webbrowser

            webbrowser.open(API)
        except Exception:
            anotar(traceback.format_exc())


if __name__ == "__main__":
    main()
