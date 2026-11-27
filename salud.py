"""Servidor HTTP minimo para que un host tipo Render mantenga el proceso vivo."""

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot Pudin activo")

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args) -> None:
        pass


def iniciar() -> HTTPServer | None:
    puerto = int(os.environ.get("PORT", "0") or 0)
    if not puerto:
        return None
    servidor = HTTPServer(("0.0.0.0", puerto), _Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    print(f"[salud] escuchando en 0.0.0.0:{puerto}")
    return servidor
