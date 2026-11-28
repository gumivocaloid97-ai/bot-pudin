"""Cierra TODAS las copias del bot abiertas en esta carpeta y deja todo limpio.

Mira la ruta del ejecutable, no solo el comando: tambien mata lo que se
abrio a mano desde una ventana de cmd.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def cerrar_copias() -> None:
    orden = (
        f"$r = '{BASE}'.ToLower(); $n = 0;"
        " Get-CimInstance Win32_Process | Where-Object {"
        " $_.Name -like 'python*' -and $_.ProcessId -ne $PID -and ("
        " ($_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($r)) -or"
        " ($_.CommandLine -and $_.CommandLine.ToLower().Contains($r)) ) } |"
        " ForEach-Object { $n++; Write-Host ('  cerrado ' + $_.ProcessId);"
        " Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue };"
        " Write-Host ('  copias cerradas: ' + $n)"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", orden],
        check=False,
    )


def main() -> None:
    print()
    print("  Limpiando todas las copias del bot...")
    print()
    if sys.platform != "win32":
        print("  Esto es solo para Windows.")
        return

    cerrar_copias()

    for basura in ("detener.txt",):
        ruta = BASE / basura
        if ruta.exists():
            try:
                ruta.unlink()
            except OSError:
                pass

    print()
    print("  Listo. Ahora arrancá con Pudin.bat (una sola vez).")
    print()


if __name__ == "__main__":
    main()
