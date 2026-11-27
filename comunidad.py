"""Encuestas, recordatorios, cumpleanos, contador de miembros y bienvenida."""

from __future__ import annotations

import io
import json
import logging
import time
from datetime import date
from pathlib import Path

import discord

log = logging.getLogger("pudin")

CARPETA = Path(__file__).resolve().parent
ARCHIVO_ENCUESTAS = CARPETA / "encuestas.json"
ARCHIVO_RECORDATORIOS = CARPETA / "recordatorios.json"
ARCHIVO_CUMPLES = CARPETA / "cumples.json"
ARCHIVO_CONTADOR = CARPETA / "contador.json"


def _leer(archivo: Path, defecto):
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except Exception:
        return defecto


def _guardar(archivo: Path, datos) -> None:
    try:
        archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as error:
        log.warning("No pude guardar %s: %s", archivo.name, error)


# --- encuestas -------------------------------------------------------------


def crear_encuesta(pregunta: str, opciones: list[str], autor: str) -> str:
    datos = _leer(ARCHIVO_ENCUESTAS, {})
    ident = str(int(time.time() * 1000))
    datos[ident] = {"pregunta": pregunta, "opciones": opciones, "votos": {}, "autor": autor}
    _guardar(ARCHIVO_ENCUESTAS, datos)
    return ident


def embed_encuesta(ident: str) -> discord.Embed | None:
    encuesta = _leer(ARCHIVO_ENCUESTAS, {}).get(ident)
    if not encuesta:
        return None
    conteo = [0] * len(encuesta["opciones"])
    votos = encuesta["votos"]
    for indice in votos.values():
        if 0 <= indice < len(conteo):
            conteo[indice] += 1
    total = len(votos)
    lineas = []
    for posicion, opcion in enumerate(encuesta["opciones"]):
        parte = (conteo[posicion] / total * 100) if total else 0.0
        lleno = round(parte / 10)
        barra = "█" * lleno + "░" * (10 - lleno)
        lineas.append(f"**{opcion}**\n`{barra}` {conteo[posicion]} · {parte:.0f}%")
    embed = discord.Embed(
        title=f"📊 {encuesta['pregunta']}", description="\n\n".join(lineas), color=0x3498DB
    )
    embed.set_footer(text=f"{total} voto{'s' if total != 1 else ''} · por {encuesta['autor']}")
    return embed


def votar(ident: str, usuario_id: int, indice: int) -> bool:
    datos = _leer(ARCHIVO_ENCUESTAS, {})
    encuesta = datos.get(ident)
    if not encuesta or not (0 <= indice < len(encuesta["opciones"])):
        return False
    encuesta["votos"][str(usuario_id)] = indice
    _guardar(ARCHIVO_ENCUESTAS, datos)
    return True


class BotonVoto(discord.ui.Button):
    def __init__(self, ident: str, indice: int, etiqueta: str) -> None:
        super().__init__(
            label=etiqueta[:80],
            style=discord.ButtonStyle.secondary,
            custom_id=f"enc_{ident}_{indice}",
        )
        self.ident = ident
        self.indice = indice

    async def callback(self, interaction: discord.Interaction) -> None:
        if not votar(self.ident, interaction.user.id, self.indice):
            await interaction.response.send_message("Esa encuesta ya no existe.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=embed_encuesta(self.ident), view=self.view
        )


class VistaEncuesta(discord.ui.View):
    def __init__(self, ident: str) -> None:
        super().__init__(timeout=None)
        encuesta = _leer(ARCHIVO_ENCUESTAS, {}).get(ident)
        if not encuesta:
            return
        for indice, opcion in enumerate(encuesta["opciones"][:5]):
            self.add_item(BotonVoto(ident, indice, opcion))


def registrar_vistas(client: discord.Client) -> int:
    vistas = 0
    for ident in _leer(ARCHIVO_ENCUESTAS, {}):
        try:
            client.add_view(VistaEncuesta(ident))
            vistas += 1
        except Exception as error:
            log.warning("No pude restaurar la encuesta %s: %s", ident, error)
    return vistas


# --- recordatorios ---------------------------------------------------------

UNIDADES = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def leer_duracion(texto: str) -> int | None:
    texto = (texto or "").strip().lower().replace(" ", "")
    if not texto:
        return None
    if texto[-1] in UNIDADES and texto[:-1].isdigit():
        return int(texto[:-1]) * UNIDADES[texto[-1]]
    if texto.isdigit():
        return int(texto) * 60
    return None


def agregar_recordatorio(
    usuario_id: int,
    canal_id: int | None,
    guild_id: int | None,
    cuando: float,
    texto: str,
) -> int:
    datos = _leer(ARCHIVO_RECORDATORIOS, [])
    ident = int(time.time() * 1000)
    datos.append(
        {
            "id": ident,
            "usuario": usuario_id,
            "canal": canal_id,
            "guild": guild_id,
            "cuando": cuando,
            "texto": texto,
        }
    )
    _guardar(ARCHIVO_RECORDATORIOS, datos)
    return ident


def recordatorios_vencidos(ahora: float | None = None) -> list[dict]:
    ahora = ahora or time.time()
    return [r for r in _leer(ARCHIVO_RECORDATORIOS, []) if r["cuando"] <= ahora]


def borrar_recordatorio(ident: int) -> None:
    datos = [r for r in _leer(ARCHIVO_RECORDATORIOS, []) if r["id"] != ident]
    _guardar(ARCHIVO_RECORDATORIOS, datos)


# --- cumpleanos ------------------------------------------------------------


def guardar_cumple(guild_id: int, usuario_id: int, dia: int, mes: int) -> None:
    datos = _leer(ARCHIVO_CUMPLES, {})
    datos.setdefault(str(guild_id), {})[str(usuario_id)] = {
        "dia": dia,
        "mes": mes,
        "ultimo": "",
    }
    _guardar(ARCHIVO_CUMPLES, datos)


def cumple_de(guild_id: int, usuario_id: int) -> dict | None:
    return _leer(ARCHIVO_CUMPLES, {}).get(str(guild_id), {}).get(str(usuario_id))


def cumples_pendientes(guild_id: int, hoy: date) -> list[int]:
    pendientes = []
    for usuario, datos in _leer(ARCHIVO_CUMPLES, {}).get(str(guild_id), {}).items():
        if datos.get("dia") == hoy.day and datos.get("mes") == hoy.month:
            if datos.get("ultimo") != hoy.isoformat():
                pendientes.append(int(usuario))
    return pendientes


def marcar_cumple_anunciado(guild_id: int, usuario_id: int, hoy: date) -> None:
    datos = _leer(ARCHIVO_CUMPLES, {})
    registro = datos.get(str(guild_id), {}).get(str(usuario_id))
    if registro is None:
        return
    registro["ultimo"] = hoy.isoformat()
    _guardar(ARCHIVO_CUMPLES, datos)


# --- contador de miembros --------------------------------------------------


def guardar_canal_contador(guild_id: int, canal_id: int | None) -> None:
    datos = _leer(ARCHIVO_CONTADOR, {})
    if canal_id is None:
        datos.pop(str(guild_id), None)
    else:
        datos[str(guild_id)] = canal_id
    _guardar(ARCHIVO_CONTADOR, datos)


def canal_contador(guild_id: int) -> int | None:
    return _leer(ARCHIVO_CONTADOR, {}).get(str(guild_id))


def nombre_contador(guild: discord.Guild) -> str:
    humanos = sum(1 for miembro in guild.members if not miembro.bot)
    return f"👥・miembros: {humanos}"


# --- bienvenida ------------------------------------------------------------


def _fuente(tamano: int):
    from PIL import ImageFont

    for nombre in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    return ImageFont.load_default()


def _limpiar(texto: str) -> str:
    """Saca emojis: las fuentes de Windows no los dibujan."""
    letras = [
        letra
        for letra in texto
        if letra.isascii() or "\u00c0" <= letra <= "\u024f" or letra in "·"
    ]
    return "".join(letras).strip()


def _recortar(texto: str, limite: int) -> str:
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


async def tarjeta_bienvenida(miembro: discord.Member, numero: int) -> discord.File | None:
    """Devuelve la tarjeta, o None si falta Pillow o falla algo."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    try:
        datos = await miembro.display_avatar.with_size(256).with_format("png").read()
    except Exception as error:
        log.warning("No pude bajar el avatar de %s: %s", miembro, error)
        return None

    ancho, alto = 900, 280
    try:
        fondo = Image.new("RGB", (ancho, alto))
        dibujo = ImageDraw.Draw(fondo)
        for x in range(ancho):
            mezcla = x / ancho
            dibujo.line(
                [(x, 0), (x, alto)],
                fill=(
                    int(32 + 30 * mezcla),
                    int(22 + 25 * mezcla),
                    int(58 + 12 * mezcla),
                ),
            )
        dibujo.rectangle([0, alto - 6, ancho, alto], fill=(241, 196, 15))

        avatar = Image.open(io.BytesIO(datos)).convert("RGBA").resize((180, 180))
        mascara = Image.new("L", (180, 180), 0)
        ImageDraw.Draw(mascara).ellipse((0, 0, 180, 180), fill=255)
        aro = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(aro).ellipse((0, 0, 199, 199), outline=(241, 196, 15, 255), width=6)
        fondo.paste(avatar, (50, 40), mascara)
        fondo.paste(aro, (40, 30), aro)

        dibujo.text(
            (280, 80),
            _recortar(_limpiar(miembro.display_name), 20),
            font=_fuente(46),
            fill=(255, 255, 255),
        )
        dibujo.text(
            (280, 145), f"Miembro #{numero}", font=_fuente(28), fill=(241, 196, 15)
        )
        dibujo.text(
            (280, 190),
            _recortar(_limpiar(miembro.guild.name), 34),
            font=_fuente(24),
            fill=(190, 190, 205),
        )

        salida = io.BytesIO()
        fondo.save(salida, "PNG")
        salida.seek(0)
        return discord.File(salida, filename="bienvenida.png")
    except Exception as error:
        log.warning("No pude armar la tarjeta de bienvenida: %s", error)
        return None
