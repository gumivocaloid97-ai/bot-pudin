"""Declaracion de edad: mayor o menor de 18."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord

log = logging.getLogger("pudin")

ROL_ADULTO = "🔞 +18"
ROL_MENOR = "🧒 -18"
GRUPOS = (ROL_ADULTO, ROL_MENOR)

# lo conecta bot.py para dejar constancia en el canal de registro
al_cambiar = None

AVISOS = Path(__file__).with_name("edad_avisos.json")
ESPERA_MINUTOS = 60
CANAL_EDAD = "✅・edad"


def rol(guild: discord.Guild, nombre: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=nombre)


def grupo_de(miembro: discord.Member) -> str | None:
    for nombre in GRUPOS:
        if any(rol.name == nombre for rol in miembro.roles):
            return nombre
    return None


def embed_panel() -> discord.Embed:
    lineas = [
        "Para cuidar a todos, necesitamos saber quién es mayor y quién es menor.",
        "Elegí tu grupo. Es un clic y queda marcado en tu perfil.",
        "",
        "**🔞 Soy mayor de 18**",
        "Quedás marcado como adulto. Se ve en la lista de miembros.",
        "",
        "**🧒 Soy menor de 18**",
        "Quedás marcado como menor. Se ve en la lista de miembros.",
        "",
        "**Sean honestos con la edad.**",
        "Si mentís y se descubre, hay sanción o ban directo.",
        "",
        "Si te equivocaste, avisale al staff y te lo cambian.",
        "No se guarda ningún dato: solo queda el rol.",
    ]
    return discord.Embed(
        title="✅ Tu edad",
        description="\n".join(lineas),
        color=0x3498DB,
    )


class PanelEdad(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _poner(
        self, interaction: discord.Interaction, nuevo: str, etiqueta: str
    ) -> None:
        guild = interaction.guild
        destino = rol(guild, nuevo)
        if destino is None:
            await interaction.response.send_message(
                "Falta el rol en el servidor. Avisale al staff.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        antes = grupo_de(interaction.user)
        actuales = [r for r in interaction.user.roles if r.name in GRUPOS]
        try:
            if actuales:
                await interaction.user.remove_roles(*actuales, reason="Cambio de grupo de edad")
            await interaction.user.add_roles(destino, reason="Declaracion de edad")
        except discord.Forbidden:
            await interaction.followup.send(
                "No pude darte el rol. Avisale al staff.", ephemeral=True
            )
            return

        if nuevo == ROL_ADULTO:
            await interaction.followup.send(
                "Listo, quedaste como **mayor de 18**. Ya podés entrar al canal de adultos.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "Listo, quedaste como **menor de 18**. Gracias por avisar.",
                ephemeral=True,
            )
        if al_cambiar is not None:
            try:
                await al_cambiar(interaction.user, antes, etiqueta)
            except Exception as error:
                log.warning("No pude registrar el cambio de edad: %s", error)

    @discord.ui.button(
        label="Soy mayor de 18",
        emoji="🔞",
        style=discord.ButtonStyle.danger,
        custom_id="pudin_edad_adulto",
    )
    async def adulto(self, interaction: discord.Interaction, boton: discord.ui.Button) -> None:
        await self._poner(interaction, ROL_ADULTO, "mayor de 18")

    @discord.ui.button(
        label="Soy menor de 18",
        emoji="🧒",
        style=discord.ButtonStyle.primary,
        custom_id="pudin_edad_menor",
    )
    async def menor(self, interaction: discord.Interaction, boton: discord.ui.Button) -> None:
        await self._poner(interaction, ROL_MENOR, "menor de 18")


def _leer_avisos() -> dict:
    try:
        return json.loads(AVISOS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _clave(guild_id: int, user_id: int) -> str:
    return f"{guild_id}-{user_id}"


def ya_avisado(guild_id: int, user_id: int) -> bool:
    return _clave(guild_id, user_id) in _leer_avisos()


def marcar_avisado(guild_id: int, user_id: int) -> None:
    datos = _leer_avisos()
    datos[_clave(guild_id, user_id)] = datetime.now(timezone.utc).isoformat()
    try:
        AVISOS.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        log.warning("No pude guardar el aviso de edad: %s", error)


def falta_elegir(miembro: discord.Member, ahora: datetime | None = None) -> bool:
    """True si es humano, entro hace rato y todavia no tiene grupo."""
    if miembro.bot or grupo_de(miembro) is not None:
        return False
    ahora = ahora or datetime.now(timezone.utc)
    entro = miembro.joined_at
    if entro is not None and (ahora - entro) < timedelta(minutes=ESPERA_MINUTOS):
        return False
    return True


def faltantes(guild: discord.Guild) -> list[discord.Member]:
    return [m for m in guild.members if falta_elegir(m)]


def _mensaje(guild: discord.Guild) -> discord.Embed:
    canal = discord.utils.get(guild.text_channels, name=CANAL_EDAD)
    donde = canal.mention if canal is not None else "el canal de edad"
    return discord.Embed(
        title=f"Falta un paso en {guild.name}",
        description=(
            f"Todavía no elegiste tu grupo de edad.\n\n"
            f"Entrá a {donde} y tocá el botón: **mayor de 18** o **menor de 18**.\n"
            "Es un clic. No se guarda ningún dato, solo queda el rol.\n\n"
            "**Sean honestos con la edad.** Si mentís y se descubre, hay sanción o ban directo."
        ),
        color=0x3498DB,
    )


async def avisar_faltantes(guild: discord.Guild, repetir: bool = False) -> tuple[int, int, list[str]]:
    """Manda privado a quien no eligio. Devuelve (enviados, fallidos, nombres)."""
    enviados = 0
    fallidos = 0
    nombres = []
    embed = _mensaje(guild)
    for miembro in faltantes(guild):
        if not repetir and ya_avisado(guild.id, miembro.id):
            continue
        nombres.append(miembro.display_name)
        try:
            await miembro.send(embed=embed)
            enviados += 1
        except discord.HTTPException:
            fallidos += 1
        marcar_avisado(guild.id, miembro.id)
    return enviados, fallidos, nombres
