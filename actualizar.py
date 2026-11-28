"""Auto-actualizacion: baja los .py nuevos desde GitHub."""
from __future__ import annotations

import os
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "gumivocaloid97-ai/bot-pudin"
API = f"https://api.github.com/repos/{REPO}/contents"
CRUDO = f"https://raw.githubusercontent.com/{REPO}/main"
ARCHIVOS = (
    "bot.py", "musica.py", "niveles.py", "salud.py", "actualizar.py",
    "vigilancia.py", "donaciones.py", "comunidad.py", "tickets.py",
    "colores.py", "edad.py", "radio.py", "supervisor.py", "inicio.py",
    "Iniciar Oculto.vbs", "Arrancar Bot.bat", "Detener Bot.bat",
    "Ver Registro.bat", "Instalar Inicio Automatico.bat",
    "Quitar Inicio Automatico.bat", "bandeja.py", "icono.png",
    "panel.py", "panel.html", "Panel.bat", "app.py",
)
ESPERA = 20

CARPETA = Path(__file__).resolve().parent
VERSION_LOCAL = CARPETA / "version.txt"
AGENTE = f"BotPudin (https://github.com/{REPO})"


def _contexto():
    """El Python portable a veces no tiene los certificados del sistema."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def _bajar(url: str, extra: dict) -> bytes:
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, **extra})
    try:
        with urllib.request.urlopen(pedido, timeout=ESPERA, context=_contexto()) as respuesta:
            return respuesta.read()
    except TypeError:
        with urllib.request.urlopen(pedido, timeout=ESPERA) as respuesta:
            return respuesta.read()


def _descargar(nombre: str) -> bytes:
    # los nombres con espacios tienen que ir codificados en la URL
    ruta = urllib.parse.quote(nombre)
    try:
        return _bajar(f"{API}/{ruta}?ref=main", {"Accept": "application/vnd.github.raw"})
    except Exception:
        return _bajar(f"{CRUDO}/{ruta}", {})


def version_local() -> str:
    if VERSION_LOCAL.exists():
        return VERSION_LOCAL.read_text(encoding="utf-8").strip()
    return ""


def version_remota() -> str:
    return _descargar("version.txt").decode("utf-8", "replace").strip()


def buscar() -> bool:
    """True si descargo una version nueva."""
    try:
        remota = version_remota()
    except Exception as error:
        print(f"[actualizar] no pude consultar la version: {error!r}")
        return False

    local = version_local()
    if not remota or remota == local:
        return False

    print(f"[actualizar] version nueva: {remota} (tenias {local or 'ninguna'})")
    nuevos = {}
    for nombre in ARCHIVOS:
        try:
            datos = _descargar(nombre)
        except Exception as error:
            print(f"[actualizar] fallo {nombre}: {error!r}")
            return False
        if nombre.endswith(".py"):
            try:
                compile(datos, nombre, "exec")
            except SyntaxError as error:
                print(f"[actualizar] {nombre} vino roto ({error}), cancelo")
                return False
        nuevos[nombre] = datos

    try:
        for nombre, datos in nuevos.items():
            (CARPETA / nombre).write_bytes(datos)
        VERSION_LOCAL.write_text(remota, encoding="utf-8")
    except OSError as error:
        print(f"[actualizar] no pude escribir los archivos: {error!r}")
        return False
    print("[actualizar] archivos actualizados")
    return True


def faltantes() -> list[str]:
    return [nombre for nombre in ARCHIVOS if not (CARPETA / nombre).exists()]


def reparar() -> bool:
    """Baja los archivos que falten, aunque la version sea la misma."""
    faltan = faltantes()
    if not faltan:
        return False
    print(f"[actualizar] faltan archivos: {', '.join(faltan)}")
    for nombre in faltan:
        try:
            datos = _descargar(nombre)
        except Exception as error:
            print(f"[actualizar] no pude bajar {nombre}: {error!r}")
            return False
        try:
            if nombre.endswith(".py"):
                compile(datos, nombre, "exec")
            (CARPETA / nombre).write_bytes(datos)
        except (SyntaxError, OSError) as error:
            print(f"[actualizar] {nombre} no se pudo guardar: {error!r}")
            return False
        print(f"[actualizar] recuperado {nombre}")
    return True


def reiniciar() -> None:
    try:
        os.execv(sys.executable, [sys.executable, str(CARPETA / "bot.py")])
    except Exception as error:
        print(f"[actualizar] cerra y volve a abrir el bot a mano: {error!r}")
        sys.exit(0)


PAQUETES_URL = f"{CRUDO}/paquetes.zip"
PAQUETES = ("pystray", "PIL", "six")


def faltan_paquetes() -> bool:
    """True si el icono de la bandeja no tiene con que arrancar."""
    for nombre in PAQUETES:
        try:
            __import__(nombre)
        except ImportError:
            return True
    return False


def asegurar_paquetes() -> bool:
    """Baja pystray y Pillow a la carpeta del runtime la primera vez."""
    if sys.platform != "win32" or not faltan_paquetes():
        return False
    destino = Path(sys.prefix) / "Lib" / "site-packages"
    if not destino.is_dir():
        print(f"[paquetes] no encontre {destino}")
        return False
    temporal = CARPETA / "paquetes.zip"
    print("[paquetes] bajando lo que falta para el icono de la bandeja...")
    try:
        datos = _bajar(PAQUETES_URL, {})
        temporal.write_bytes(datos)
        import zipfile

        with zipfile.ZipFile(temporal) as z:
            z.extractall(destino)
        print(f"[paquetes] listo: {len(datos) // 1024} KB en {destino}")
        return True
    except Exception as error:
        print(f"[paquetes] no pude instalarlos: {error!r}")
        return False
    finally:
        try:
            temporal.unlink()
        except OSError:
            pass
