"""Revisa como esta todo y deja el resultado en diagnostico.txt."""

from __future__ import annotations

import json
import socket
import sys
import urllib.request
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
SALIDA = CARPETA / "diagnostico.txt"

ARCHIVOS = (
    "bot.py", "app.py", "pudin.py", "panel.py", "panel.html", "bandeja.py",
    "supervisor.py", "inicio.py", "icono.png", "version.txt", "ia.py", "latencia.py",
    "limpiar.py", "pudin.py", "ia.py",
)
RUNTIME = (
    "python.exe", "pythonw.exe", "python312.dll", "_tkinter.pyd",
    "tcl86t.dll", "tk86t.dll", "zlib1.dll", "vcruntime140.dll",
)


def puerto_abierto(puerto: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=0.6):
            return True
    except OSError:
        return False


def cola(ruta: Path, cantidad: int = 40) -> list[str]:
    try:
        return ruta.read_text(encoding="utf-8", errors="replace").splitlines()[-cantidad:]
    except OSError:
        return ["(no existe)"]


def main() -> None:
    raiz_runtime = Path(sys.prefix)
    sitio = raiz_runtime / "Lib" / "site-packages"
    lineas: list[str] = []

    def anotar(texto: str = "") -> None:
        lineas.append(texto)

    anotar("=== DIAGNOSTICO BOT PUDIN ===")
    anotar(f"carpeta    : {CARPETA}")
    anotar(f"python     : {sys.version.split()[0]}")
    anotar(f"prefijo    : {raiz_runtime}")
    try:
        anotar(f"version    : {(CARPETA / 'version.txt').read_text(encoding='utf-8').strip()}")
    except OSError:
        anotar("version    : (falta version.txt)")

    anotar("")
    anotar("--- archivos del bot ---")
    for nombre in ARCHIVOS:
        ruta = CARPETA / nombre
        anotar(f"  {nombre:14} {'OK' if ruta.exists() else 'FALTA':6}"
               f"{(ruta.stat().st_size if ruta.exists() else 0):>9} bytes")

    anotar("")
    anotar("--- runtime de la ventana ---")
    for nombre in RUNTIME:
        anotar(f"  {nombre:18} {'OK' if (raiz_runtime / nombre).exists() else 'FALTA'}")
    tcl = raiz_runtime / "tcl" / "tcl8.6" / "init.tcl"
    paquete = sitio / "tkinter" / "__init__.py"
    anotar(f"  {'tcl/':18} {'OK' if tcl.exists() else 'FALTA'}")
    anotar(f"  {'tkinter/':18} {'OK' if paquete.exists() else 'FALTA'}")

    anotar("")
    anotar("--- icono en la bandeja (PC) ---")
    for modulo in ("pystray", "PIL"):
        try:
            __import__(modulo)
            anotar(f"  {modulo:8}: OK")
        except Exception as error:  # noqa: BLE001
            anotar(f"  {modulo:8}: FALTA ({error}) -> corré Instalar Pillow.bat")
    anotar(f"  icono.png : {'SI' if (CARPETA / 'icono.png').exists() else 'NO'}")
    anotar("  Si la libreria esta OK y no ves el icono, puede estar en la flechita ^ de la barra.")

    anotar("")
    anotar("--- IA ---")
    try:
        import ia

        anotar(f"  clave      : {'SI' if ia.configurada() else 'NO (respuestas basicas)'}")
        anotar(f"  proveedor  : {ia.proveedor()}")
        anotar(f"  modelo     : {ia.modelo()}")
    except Exception as error:
        anotar(f"  ia.py      : ERROR {error!r}")

    anotar("")
    anotar("--- probando la ventana ---")
    try:
        import tkinter

        anotar(f"  import tkinter : OK (Tk {tkinter.TkVersion})")
        try:
            prueba = tkinter.Tk()
            prueba.withdraw()
            prueba.destroy()
            anotar("  abrir ventana  : OK")
        except Exception as error:
            anotar(f"  abrir ventana  : ERROR {error!r}")
    except Exception as error:
        anotar(f"  import tkinter : ERROR {error!r}")

    anotar("")
    anotar("--- puertos ---")
    for puerto, nombre in ((47777, "candado del bot"), (8777, "panel"), (8778, "ventana")):
        anotar(f"  {puerto} ({nombre}): {'abierto' if puerto_abierto(puerto) else 'cerrado'}")

    anotar("")
    anotar("--- el bot ---")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8777/api/estado", timeout=2) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        anotar(f"  responde si, version {datos.get('version')}, "
               f"{len(datos.get('servidores', []))} servidores")
    except Exception as error:
        anotar(f"  no responde ({error!r})")

    anotar("")
    anotar("--- bot.log (ultimas 40) ---")
    lineas.extend(cola(CARPETA / "bot.log"))
    anotar("")
    anotar("--- panel.log (ultimas 40) ---")
    lineas.extend(cola(CARPETA / "panel.log"))

    texto = "\n".join(lineas)
    SALIDA.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"\nGuardado en {SALIDA}")
    try:
        input("\nEnter para cerrar...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
