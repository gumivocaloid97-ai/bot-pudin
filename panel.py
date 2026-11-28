"""Panel de control del bot: una pagina local con botones y registro en vivo.

Se levanta dentro del mismo proceso del bot y solo escucha en 127.0.0.1.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
REGISTRO = CARPETA / "bot.log"
PAGINA = CARPETA / "panel.html"
ICONO = CARPETA / "icono.png"
PUERTO = 8777

log = logging.getLogger("pudin")

_ACCION = {"cuando": 0.0, "cual": ""}
SEGUNDOS_ENTRE_ACCIONES = 12


def _accion_ocupada(nombre: str) -> bool:
    """Evita que varios clics seguidos disparen reinicios en paralelo."""
    if time.time() - _ACCION["cuando"] < SEGUNDOS_ENTRE_ACCIONES:
        return True
    _ACCION["cuando"] = time.time()
    _ACCION["cual"] = nombre
    return False

try:
    import latencia
except ModuleNotFoundError:
    latencia = None

try:
    import ia as ia_modulo
except ModuleNotFoundError:
    ia_modulo = None

_arranque = time.time()


def _version() -> str:
    try:
        return (CARPETA / "version.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return "?"


def _abrir(ruta: Path) -> bool:
    if not ruta.exists():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(ruta))  # type: ignore[attr-defined]
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(ruta)])
        return True
    except OSError as error:
        log.warning("No pude abrir %s: %s", ruta, error)
        return False


def _ultimas_lineas(cantidad: int) -> list[str]:
    try:
        with REGISTRO.open("rb") as archivo:
            archivo.seek(0, os.SEEK_END)
            tamano = archivo.tell()
            archivo.seek(max(0, tamano - 96 * 1024))
            texto = archivo.read().decode("utf-8", "replace")
    except OSError:
        return []
    return texto.splitlines()[-cantidad:]


async def iniciar(cliente, arbol=None) -> bool:
    """Prende el panel. Si el puerto esta ocupado o falta aiohttp, el bot sigue igual."""
    try:
        from aiohttp import web
    except ImportError as error:
        log.info("Sin panel de control: %s", error)
        return False

    async def pagina(_peticion):
        try:
            return web.FileResponse(PAGINA)
        except Exception:
            return web.Response(text="Falta panel.html", status=500)

    async def icono(_peticion):
        if not ICONO.exists():
            return web.Response(status=404)
        return web.FileResponse(ICONO)

    async def estado(_peticion):
        servidores = [
            {"nombre": gremio.name, "miembros": gremio.member_count or 0}
            for gremio in cliente.guilds
        ]
        red = cliente.latency
        return web.json_response(
            {
                "version": _version(),
                "usuario": str(cliente.user) if cliente.user else "",
                "conectado": cliente.is_ready(),
                "servidores": servidores,
                "miembros": sum(s["miembros"] for s in servidores),
                "comandos": len(arbol.get_commands()) if arbol is not None else 0,
                "ping": int(red * 1000) if red else 0,
                "bucle": round(latencia.ultimo(), 1) if latencia is not None else 0.0,
                "ia": ia_modulo.resumen() if ia_modulo is not None else "sin modulo",
                "encendido": int(time.time() - _arranque),
                "desde": datetime.fromtimestamp(_arranque).strftime("%d/%m %H:%M"),
            }
        )

    async def registro(peticion):
        try:
            cantidad = int(peticion.query.get("lineas", 150))
        except ValueError:
            cantidad = 150
        return web.json_response({"lineas": _ultimas_lineas(max(10, min(cantidad, 500)))})

    async def carpeta(_peticion):
        listo = _abrir(CARPETA)
        return web.json_response(
            {"mensaje": "Abrí la carpeta." if listo else "No pude abrir la carpeta."}
        )

    async def ver_registro(_peticion):
        listo = _abrir(REGISTRO)
        return web.json_response(
            {"mensaje": "Abrí bot.log." if listo else "Todavía no hay bot.log."}
        )

    async def despues(cerrar: bool) -> None:
        await asyncio.sleep(0.4)
        if cerrar:
            await cliente.close()
        import actualizar

        actualizar.reiniciar()

    async def reiniciar(_peticion):
        if _accion_ocupada("reiniciar"):
            return web.json_response(
                {"mensaje": "Ya hay una acción en curso. Esperá unos segundos."}, status=409
            )
        log.info("Reinicio pedido desde el panel")
        asyncio.create_task(despues(cerrar=True))
        return web.json_response({"mensaje": "Reiniciando el bot…"})

    async def actualizar(_peticion):
        if _accion_ocupada("actualizar"):
            return web.json_response(
                {"mensaje": "Ya hay una acción en curso. Esperá unos segundos."}, status=409
            )
        log.info("Actualizacion pedida desde el panel")
        asyncio.create_task(despues(cerrar=True))
        return web.json_response({"mensaje": "Reiniciando y buscando versión nueva…"})

    async def detener(_peticion):
        if _accion_ocupada("detener"):
            return web.json_response(
                {"mensaje": "Ya hay una acción en curso. Esperá unos segundos."}, status=409
            )
        log.info("Apagado pedido desde el panel")
        try:
            (CARPETA / "detener.txt").write_text("apagado desde el panel", encoding="utf-8")
        except OSError as error:
            log.warning("No pude escribir detener.txt: %s", error)
        asyncio.create_task(despues(cerrar=True))
        return web.json_response(
            {"mensaje": "Apagando. Queda apagado hasta que aprietes Arrancar el bot."}
        )

    aplicacion = web.Application()
    aplicacion["cliente"] = cliente
    aplicacion.router.add_get("/", pagina)
    aplicacion.router.add_get("/icono.png", icono)
    aplicacion.router.add_get("/api/estado", estado)
    aplicacion.router.add_get("/api/log", registro)
    aplicacion.router.add_post("/api/reiniciar", reiniciar)
    aplicacion.router.add_post("/api/actualizar", actualizar)
    aplicacion.router.add_post("/api/detener", detener)
    aplicacion.router.add_post("/api/carpeta", carpeta)
    aplicacion.router.add_post("/api/registro", ver_registro)

    servidor = web.AppRunner(aplicacion, access_log=None)
    await servidor.setup()
    try:
        await web.TCPSite(servidor, "127.0.0.1", PUERTO).start()
    except OSError as error:
        log.warning("El panel no pudo abrir el puerto %s: %s", PUERTO, error)
        await servidor.cleanup()
        return False
    log.info("Panel listo en http://127.0.0.1:%s", PUERTO)
    return True
