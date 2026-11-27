"""Radio fija: un dia y una hora, aviso en anuncios y arranque automatico."""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord

log = logging.getLogger("pudin.radio")

CONFIG = Path(__file__).with_name("radio.json")
ZONA = timezone(timedelta(hours=-3), "ART")
DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
CANAL_VOZ = "🎙️・radio-pudin"
CANAL_AVISO = "📢・anuncios"

TEMAS = [
    "Bizarrap, Quevedo - Bzrp Music Sessions #52",
    "Duki - Rockstar",
    "Bad Bunny - Tití Me Preguntó",
    "Tiago PZK, Lit Killah - Entre Nosotros",
    "La Konga - Universo Paralelo",
    "Los Palmeras - Bombón",
    "Tan Biónica - Ciudad Mágica",
    "No Te Va Gustar - A Las Nueve",
]

POR_DEFECTO = {
    "activo": True,
    "dia": 4,
    "hora": 21,
    "minuto": 0,
    "aviso": 60,
    "temas": TEMAS,
    "ultimo_aviso": "",
    "ultimo_arranque": "",
}


def cargar() -> dict:
    if not CONFIG.exists():
        guardar(POR_DEFECTO)
        return dict(POR_DEFECTO)
    try:
        datos = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(POR_DEFECTO)
    for clave, valor in POR_DEFECTO.items():
        datos.setdefault(clave, valor)
    return datos


def guardar(datos: dict) -> None:
    CONFIG.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def ahora() -> datetime:
    return datetime.now(ZONA)


def cuando(datos: dict) -> str:
    return f"{DIAS[datos['dia']].capitalize()} a las {datos['hora']:02d}:{datos['minuto']:02d}"


def proxima(datos: dict) -> datetime:
    """La proxima vez que toca, en hora argentina."""
    t = ahora()
    objetivo = t.replace(hour=datos["hora"], minute=datos["minuto"], second=0, microsecond=0)
    dias = (datos["dia"] - t.weekday()) % 7
    if dias == 0 and t >= objetivo:
        dias = 7
    return objetivo + timedelta(days=dias)


def _canal(guild: discord.Guild, nombre: str):
    return discord.utils.get(guild.text_channels, name=nombre)


def _voz(guild: discord.Guild, nombre: str):
    return discord.utils.get(guild.voice_channels, name=nombre)


def embed_aviso(datos: dict, previo: bool, mencion_voz: str) -> discord.Embed:
    proxima_vez = proxima(datos)
    if previo:
        titulo = "📻 La radio arranca en un rato"
        texto = (
            f"Hoy a las **{datos['hora']:02d}:{datos['minuto']:02d}** empieza la radio.\n"
            f"Entrá a {mencion_voz} y quedate."
        )
    else:
        titulo = "📻 Radio Pudin, en vivo"
        texto = (
            f"Ya está sonando en {mencion_voz}.\n"
            f"Son {len(datos['temas'])} temas en rotación. Entrá y escuchá."
        )
    embed = discord.Embed(
        title=titulo,
        description=texto,
        color=0x1ABC9C,
        timestamp=proxima_vez,
    )
    embed.add_field(name="Próxima", value=f"<t:{int(proxima_vez.timestamp())}:F>", inline=True)
    embed.set_footer(text="Radio Pudin")
    return embed


async def anunciar(guild: discord.Guild, datos: dict, previo: bool) -> None:
    canal = _canal(guild, CANAL_AVISO)
    if canal is None:
        return
    voz = _voz(guild, CANAL_VOZ)
    embed = embed_aviso(datos, previo, voz.mention if voz else f"`{CANAL_VOZ}`")
    try:
        await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        log.error("No pude anunciar la radio en %s", canal)


async def arrancar(guild: discord.Guild, reproductor, datos: dict) -> str:
    """Conecta al canal de radio y pone los temas en rotacion."""
    voz = _voz(guild, CANAL_VOZ)
    if voz is None:
        return "falta el canal de voz"
    if reproductor.voz is not None and reproductor.voz.is_playing():
        return "ya estaba sonando"
    if not datos["temas"]:
        return "no hay temas cargados"

    try:
        await reproductor.asegurar_conexion(voz)
    except Exception as error:
        log.error("No pude entrar al canal de radio: %s", error)
        return "no pude entrar al canal"

    temas = list(datos["temas"])
    random.shuffle(temas)
    pistas = []
    for tema in temas[:10]:
        try:
            encontradas = await reproductor.buscar(tema)
        except Exception as error:
            log.warning("No encontre %s: %s", tema, error)
            continue
        if encontradas:
            pistas.append(encontradas[0])

    if not pistas:
        return "no encontre ningun tema"

    reproductor.repeticion = "cola"
    canal_texto = _canal(guild, CANAL_VOZ) or _canal(guild, CANAL_AVISO)
    await reproductor.encolar(pistas, canal_texto, "Radio Pudin")
    return f"{len(pistas)} temas"


async def revisar(guild: discord.Guild, reproductor) -> str | None:
    """La llama la tarea cada minuto. Devuelve que hizo, si hizo algo."""
    datos = cargar()
    if not datos["activo"]:
        return None
    t = ahora()
    if t.weekday() != datos["dia"]:
        return None
    hoy = t.date().isoformat()
    objetivo = t.replace(hour=datos["hora"], minute=datos["minuto"], second=0, microsecond=0)

    aviso_min = datos.get("aviso") or 0
    if aviso_min and datos.get("ultimo_aviso") != hoy:
        desde = objetivo - timedelta(minutes=aviso_min)
        if desde <= t < desde + timedelta(minutes=2):
            await anunciar(guild, datos, previo=True)
            datos["ultimo_aviso"] = hoy
            guardar(datos)
            return "aviso previo"

    if datos.get("ultimo_arranque") != hoy and objetivo <= t < objetivo + timedelta(minutes=45):
        await anunciar(guild, datos, previo=False)
        datos["ultimo_arranque"] = hoy
        guardar(datos)
        resultado = await arrancar(guild, reproductor, datos)
        log.info("Radio arrancada: %s", resultado)
        return f"arranque ({resultado})"
    return None
