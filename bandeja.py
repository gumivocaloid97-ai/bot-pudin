"""Icono del bot en la bandeja del sistema, al lado del reloj.

El bot corre sin ventana; desde el icono se puede ver el registro,
reiniciarlo o apagarlo.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("pudin")

CARPETA = Path(__file__).resolve().parent
ICONO = CARPETA / "icono.png"
REGISTRO = CARPETA / "bot.log"
PUERTO_CANDADO = 47777


def _abrir(ruta: Path) -> None:
    if not ruta.exists():
        log.warning("No existe %s", ruta)
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(ruta))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(ruta)])
    except OSError as error:
        log.warning("No pude abrir %s: %s", ruta, error)


def _imagen():
    """El pudin del icono. Si falta el archivo, un cuadrado caramel."""
    from PIL import Image

    if ICONO.exists():
        return Image.open(ICONO).convert("RGBA")
    return Image.new("RGBA", (64, 64), (246, 196, 138, 255))


def iniciar(cliente) -> bool:
    """Prende el icono. Si algo falla, el bot sigue andando igual."""
    try:
        import pystray
    except Exception as error:  # falta la libreria o no hay escritorio
        log.info("Sin icono en la bandeja: %s", error)
        return False

    def estado() -> str:
        if cliente.is_ready():
            servidores = len(cliente.guilds)
            return f"Bot Pudin v2 · conectado · {servidores} servidores"
        return "Bot Pudin v2 · arrancando"

    def accion(funcion):
        def envoltura(icono, item) -> None:
            try:
                funcion()
            except Exception as error:
                log.error("Fallo la accion de la bandeja: %s", error)
        return envoltura

    def en_el_bot(corrutina) -> None:
        asyncio.run_coroutine_threadsafe(corrotina, cliente.loop)

    async def reiniciar() -> None:
        log.info("Reinicio pedido desde el icono")
        import actualizar

        await cliente.close()
        actualizar.reiniciar()

    async def apagar() -> None:
        log.info("Apagado pedido desde el icono")
        try:
            (CARPETA / "detener.txt").write_text("apagado desde el icono", encoding="utf-8")
        except OSError as error:
            log.warning("No pude escribir detener.txt: %s", error)
        await cliente.close()

    menu = pystray.Menu(
        pystray.MenuItem(estado, accion(lambda: None), enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Abrir el registro", accion(lambda: _abrir(REGISTRO)), default=True),
        pystray.MenuItem("Abrir la carpeta", accion(lambda: _abrir(CARPETA))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Reiniciar el bot", accion(lambda: en_el_bot(reiniciar()))),
        pystray.MenuItem("Apagar el bot", accion(lambda: en_el_bot(apagar()))),
    )

    try:
        icono = pystray.Icon("pudin", _imagen(), "Bot Pudin v2", menu)
    except Exception as error:
        log.warning("No pude crear el icono: %s", error)
        return False

    threading.Thread(target=icono.run, name="bandeja", daemon=True).start()
    log.info("Icono en la bandeja del sistema listo")
    return True
