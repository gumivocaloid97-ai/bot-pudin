"""Ventana del bot. Al minimizar se esconde y queda el icono en la bandeja."""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
ICONO = CARPETA / "icono.png"
PUERTO_BOT = 8777
PUERTO_VENTANA = 8778
API = f"http://127.0.0.1:{PUERTO_BOT}"

FONDO = "#101216"
PANEL = "#181b21"
PANEL2 = "#1f232b"
BORDE = "#2a2f39"
TEXTO = "#e8eaee"
TENUE = "#8b93a1"
CARAMELO = "#f6c48a"
VERDE = "#3ecf8e"
AMARILLO = "#f5a623"
ROJO = "#e5484d"

FUENTE = "Segoe UI"


def pedir(ruta: str, metodo: str = "GET") -> dict:
    pedido = urllib.request.Request(API + ruta, method=metodo)
    with urllib.request.urlopen(pedido, timeout=1.5) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def humano(segundos: int) -> str:
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}m {segundos % 60}s"
    if segundos < 86400:
        return f"{segundos // 3600}h {segundos % 3600 // 60}m"
    return f"{segundos // 86400}d {segundos % 86400 // 3600}h"


def avisar_ventana(orden: str) -> bool:
    """True si ya habia una ventana abierta y entendio la orden."""
    try:
        with socket.create_connection(("127.0.0.1", PUERTO_VENTANA), timeout=0.5) as caño:
            caño.sendall(orden.encode("utf-8"))
        return True
    except OSError:
        return False


class Ventana:
    def __init__(self, raiz: tk.Tk) -> None:
        self.raiz = raiz
        self.ordenes: queue.Queue[str] = queue.Queue()
        self.chips: list[tk.Label] = []
        self.encendido = time.time()
        self.arrancando = os.environ.get("PUDIN_ARRANCANDO") == "1"
        self.dibujar()
        self.escuchar()
        if not self.viva():
            return
        self.refrescar()
        self.leer_registro()

    def viva(self) -> bool:
        try:
            return bool(self.raiz.winfo_exists())
        except tk.TclError:
            return False

    # ---------- dibujo ----------

    def dibujar(self) -> None:
        raiz = self.raiz
        raiz.title("Bot Pudin v2")
        raiz.geometry("1060x780")
        raiz.minsize(900, 600)
        raiz.configure(bg=FONDO)
        if ICONO.exists():
            try:
                raiz.iconphoto(True, tk.PhotoImage(file=str(ICONO)))
            except tk.TclError:
                pass

        raiz.bind("<Unmap>", self.al_minimizar)
        raiz.protocol("WM_DELETE_WINDOW", self.esconder)

        envuelto = tk.Frame(raiz, bg=FONDO, padx=22, pady=18)
        envuelto.pack(fill="both", expand=True)

        cabecera = tk.Frame(envuelto, bg=FONDO)
        cabecera.pack(fill="x", pady=(0, 16))

        if ICONO.exists():
            try:
                from tkinter import PhotoImage

                self.logo = PhotoImage(file=str(ICONO))
                self.logo = self.logo.subsample(max(1, self.logo.width() // 44))
                tk.Label(cabecera, image=self.logo, bg=FONDO).pack(side="left", padx=(0, 4))
            except tk.TclError:
                tk.Label(cabecera, text="🍮", font=(FUENTE, 22), bg=FONDO, fg=CARAMELO).pack(side="left")
        else:
            tk.Label(cabecera, text="🍮", font=(FUENTE, 22), bg=FONDO, fg=CARAMELO).pack(side="left")
        titulos = tk.Frame(cabecera, bg=FONDO, padx=12)
        titulos.pack(side="left")
        tk.Label(titulos, text="Bot Pudin v2", font=(FUENTE, 16, "bold"), bg=FONDO, fg=TEXTO).pack(anchor="w")
        self.subtitulo = tk.Label(titulos, text="panel de control", font=(FUENTE, 9), bg=FONDO, fg=TENUE)
        self.subtitulo.pack(anchor="w")

        self.estado = tk.Label(
            cabecera, text="  Conectando…  ", font=(FUENTE, 10, "bold"),
            bg=PANEL2, fg=TENUE, padx=10, pady=5,
        )
        self.estado.pack(side="right")
        self.version = tk.Label(cabecera, text="v—", font=(FUENTE, 9), bg=PANEL, fg=TENUE, padx=10, pady=5)
        self.version.pack(side="right", padx=8)

        tarjetas = tk.Frame(envuelto, bg=FONDO)
        tarjetas.pack(fill="x")
        self.valores: dict[str, tk.Label] = {}
        for columna, (clave, rotulo) in enumerate(
            (
                ("servidores", "SERVIDORES"),
                ("miembros", "MIEMBROS"),
                ("comandos", "COMANDOS"),
                ("encendido", "EN LÍNEA"),
                ("ping", "LATENCIA"),
            )
        ):
            tarjetas.columnconfigure(columna, weight=1, uniform="tarjeta")
            caja = tk.Frame(tarjetas, bg=PANEL, highlightbackground=BORDE, highlightthickness=1)
            caja.grid(row=0, column=columna, sticky="nsew", padx=(0 if columna == 0 else 5, 0))
            tk.Label(caja, text=rotulo, font=(FUENTE, 7, "bold"), bg=PANEL, fg=TENUE).pack(
                anchor="w", padx=14, pady=(11, 0)
            )
            valor = tk.Label(caja, text="—", font=(FUENTE, 17, "bold"), bg=PANEL, fg=TEXTO)
            valor.pack(anchor="w", padx=14, pady=(0, 11))
            self.valores[clave] = valor

        self.servidores = tk.Frame(envuelto, bg=FONDO)
        self.servidores.pack(fill="x", pady=(12, 0))

        botones = tk.Frame(envuelto, bg=FONDO)
        botones.pack(fill="x", pady=(12, 14))
        self.boton_arrancar = self.boton(botones, "Arrancar el bot", self.arrancar, principal=True)
        self.boton_arrancar.configure(state="disabled", disabledforeground="#5c6470")
        self.boton(botones, "Reiniciar", lambda: self.accion("reiniciar", "Reiniciando el bot…"), principal=True)
        self.boton(botones, "Buscar actualización", lambda: self.accion("actualizar", "Buscando versión nueva…"))
        self.boton(botones, "Carpeta", lambda: self.accion("carpeta", "Abrí la carpeta."))
        self.boton(botones, "bot.log", lambda: self.accion("registro", "Abrí bot.log."))
        self.boton(botones, "Apagar", self.apagar, peligro=True)

        caja_registro = tk.Frame(envuelto, bg=PANEL, highlightbackground=BORDE, highlightthickness=1)
        caja_registro.pack(fill="both", expand=True)
        barra = tk.Frame(caja_registro, bg=PANEL, pady=8, padx=14)
        barra.pack(fill="x")
        tk.Label(barra, text="REGISTRO EN VIVO", font=(FUENTE, 7, "bold"), bg=PANEL, fg=TENUE).pack(side="left")
        self.cuenta = tk.Label(barra, text="—", font=(FUENTE, 8), bg=PANEL, fg=TENUE)
        self.cuenta.pack(side="right")

        self.texto = tk.Text(
            caja_registro, bg="#0c0e11", fg="#a9b2c0", font=("Consolas", 9),
            bd=0, highlightthickness=0, padx=14, pady=10, wrap="word", height=10,
        )
        self.texto.pack(fill="both", expand=True)
        self.texto.tag_configure("aviso", foreground=AMARILLO)
        self.texto.tag_configure("error", foreground="#ff8b8e")
        self.texto.tag_configure("hora", foreground="#5c6470")
        self.texto.configure(state="disabled")

        self.nota = tk.Label(envuelto, text="Se actualiza solo cada 2 segundos.", font=(FUENTE, 8),
                             bg=FONDO, fg=TENUE)
        self.nota.pack(anchor="w", pady=(8, 0))

    def boton(self, padre: tk.Frame, texto: str, accion, principal: bool = False,
              peligro: bool = False) -> tk.Button:
        if peligro:
            fondo, activo, color = "#2a1c1e", "#362325", "#ffb3b5"
        elif principal:
            fondo, activo, color = "#33261c", "#3b2b1f", CARAMELO
        else:
            fondo, activo, color = PANEL2, "#262b34", TEXTO
        boton = tk.Button(
            padre, text=texto, command=accion, font=(FUENTE, 9, "bold"),
            bg=fondo, fg=color, activebackground=activo, activeforeground=color,
            bd=0, highlightthickness=0, padx=14, pady=7, cursor="hand2", relief="flat",
        )
        boton.pack(side="left", padx=(0, 8))
        return boton

    # ---------- ventana ----------

    def al_minimizar(self, evento) -> None:
        if evento.widget is self.raiz and self.raiz.state() == "iconic":
            self.raiz.withdraw()
            self.nota.configure(text="Queda en la bandeja, al lado del reloj.")

    def esconder(self) -> None:
        self.raiz.withdraw()
        self.nota.configure(text="Queda en la bandeja, al lado del reloj.")

    def mostrar(self) -> None:
        self.raiz.deiconify()
        self.raiz.state("normal")
        self.raiz.lift()
        self.raiz.focus_force()

    def escuchar(self) -> None:
        """Una sola ventana: si ya hay otra, le pide que se muestre."""
        try:
            servidor = socket.socket()
            servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            servidor.bind(("127.0.0.1", PUERTO_VENTANA))
            servidor.listen(4)
        except OSError:
            if avisar_ventana("mostrar"):
                self.raiz.destroy()
                return
            servidor = None

        def atender() -> None:
            if servidor is None:
                return
            while True:
                try:
                    caño, _ = servidor.accept()
                except OSError:
                    return
                orden = caño.recv(64).decode("utf-8", "replace").strip()
                caño.close()
                self.ordenes.put(orden)

        if servidor is not None:
            threading.Thread(target=atender, name="ventana", daemon=True).start()

        def revisar() -> None:
            try:
                while True:
                    orden = self.ordenes.get_nowait()
                    if orden == "mostrar":
                        self.mostrar()
                    elif orden == "salir":
                        self.raiz.destroy()
                        return
            except queue.Empty:
                pass
            if self.viva():
                self.raiz.after(250, revisar)

        self.raiz.after(250, revisar)

    # ---------- acciones ----------

    def accion(self, nombre: str, mensaje: str) -> None:
        try:
            pedir(f"/api/{nombre}", metodo="POST")
            self.nota.configure(text=mensaje)
        except (urllib.error.URLError, OSError, ValueError):
            self.nota.configure(text="El bot no responde. Probalo de nuevo en un rato.")

    def apagar(self) -> None:
        from tkinter import messagebox

        if not messagebox.askyesno("Apagar", "¿Apagar el bot?\nDespués lo arrancás con Arrancar Bot.bat."):
            return
        self.accion("detener", "Apagando el bot…")

    def arrancar(self) -> None:
        try:
            import inicio

            inicio.arrancar()
            self.nota.configure(text="Arrancando el bot, dale unos segundos…")
        except Exception as error:  # noqa: BLE001
            self.nota.configure(text=f"No pude arrancarlo: {error}")

    # ---------- datos ----------

    def refrescar(self) -> None:
        if not self.viva():
            return
        try:
            datos = pedir("/api/estado")
        except (urllib.error.URLError, OSError, ValueError):
            esperando = self.arrancando and time.time() - self.encendido < 75
            if esperando:
                self.estado.configure(text="  Arrancando…  ", bg="#2e2716", fg=AMARILLO)
                self.nota.configure(text="Arrancando el bot, dale unos segundos…")
                self.boton_arrancar.configure(state="disabled")
            else:
                self.arrancando = False
                self.estado.configure(text="  Apagado  ", bg="#2e1a1c", fg=ROJO)
                self.nota.configure(text="El bot no está corriendo. Apretá Arrancar el bot.")
                self.boton_arrancar.configure(state="normal")
            self.raiz.after(2500, self.refrescar)
            return

        self.version.configure(text="v" + datos.get("version", "—"))
        if datos.get("usuario"):
            self.subtitulo.configure(text=f"{datos['usuario']} · panel de control")
        if datos.get("conectado"):
            self.estado.configure(text="  Conectado  ", bg="#17281f", fg=VERDE)
        else:
            self.estado.configure(text="  Arrancando  ", bg="#2e2716", fg=AMARILLO)

        self.valores["servidores"].configure(text=str(len(datos.get("servidores", []))))
        self.valores["miembros"].configure(text=str(datos.get("miembros", 0)))
        self.valores["comandos"].configure(text=str(datos.get("comandos", 0)))
        self.valores["encendido"].configure(text=humano(datos.get("encendido", 0)))
        self.valores["ping"].configure(text=f"{datos.get('ping', 0)} ms" if datos.get("ping") else "—")

        self.pintar_servidores(datos.get("servidores", []))

        self.arrancando = False
        self.boton_arrancar.configure(state="disabled")
        self.raiz.after(2000, self.refrescar)

    def pintar_servidores(self, servidores: list) -> None:
        while len(self.chips) < len(servidores):
            self.chips.append(
                tk.Label(self.servidores, font=(FUENTE, 8), bg=PANEL, fg="#cfd5de", padx=10, pady=4)
            )
        for chip, servidor in zip(self.chips, servidores):
            chip.configure(text=f"{servidor['nombre']}   {servidor['miembros']}")
            chip.pack(side="left", padx=(0, 6))
        for chip in self.chips[len(servidores):]:
            chip.pack_forget()

    def leer_registro(self) -> None:
        if not self.viva():
            return
        try:
            datos = pedir("/api/log?lineas=150")
            lineas = datos.get("lineas", [])
        except (urllib.error.URLError, OSError, ValueError):
            lineas = []
            self.cuenta.configure(text="sin conexión")

        if lineas:
            self.cuenta.configure(text=f"{len(lineas)} líneas")
            self.texto.configure(state="normal")
            self.texto.delete("1.0", "end")
            for linea in lineas:
                self._escribir(linea)
            self.texto.configure(state="disabled")
            self.texto.see("end")
        self.raiz.after(3000, self.leer_registro)

    def _escribir(self, linea: str) -> None:
        partes = linea.split(" ", 2)
        if len(partes) == 3 and partes[0][:4].isdigit():
            self.texto.insert("end", partes[1][:8] + " ", "hora")
            resto = partes[2]
        else:
            resto = linea
        if "ERROR" in resto[:8]:
            etiqueta = "error"
        elif "WARNING" in resto[:12]:
            etiqueta = "aviso"
        else:
            etiqueta = ""
        self.texto.insert("end", resto + "\n", etiqueta)


def main() -> None:
    raiz = tk.Tk()
    ventana = Ventana(raiz)
    if ventana.viva():
        raiz.mainloop()


if __name__ == "__main__":
    main()
