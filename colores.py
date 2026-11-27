"""Colores de nombre escalonados por meses de donacion."""

from __future__ import annotations

import logging

import discord

import donaciones

log = logging.getLogger("pudin")

COLORES = ("🔴 Rojo", "🟠 Naranja", "🟢 Verde", "🔵 Celeste", "🟣 Violeta", "🌸 Rosa")
DORADO = "👑 Dorado"
DIAS_COLOR = 60
DIAS_DORADO = 150


def es_donador(miembro: discord.abc.User) -> bool:
    permisos = getattr(miembro, "guild_permissions", None)
    if permisos is not None and permisos.administrator:
        return True
    return any("donador" in rol.name.lower() for rol in getattr(miembro, "roles", ()))


def _rol(guild: discord.Guild, nombre: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=nombre)


def dias_seguidos(conn, miembro: discord.Member) -> int:
    if conn is None or miembro.guild is None:
        return 0
    return donaciones.racha(conn, miembro.guild.id, miembro.id)


def puede_elegir(conn, miembro: discord.Member) -> tuple[bool, int]:
    if getattr(miembro.guild_permissions, "administrator", False):
        return True, DIAS_DORADO
    dias = dias_seguidos(conn, miembro)
    return dias >= DIAS_COLOR, dias


def embed_panel() -> discord.Embed:
    lineas = [
        "Elegí cómo querés que se vea tu nombre en el servidor.",
        "",
        "El color se pinta en tu nombre: arriba de cada mensaje que escribís",
        "y en la lista de miembros. El texto del mensaje no cambia, sigue blanco.",
        "",
        f"**Se abre a los {DIAS_COLOR} días seguidos de donación.**",
        f"**{DORADO}** te lo damos solo a los {DIAS_DORADO} días, y es el máximo.",
        "",
        "Podés cambiarlo las veces que quieras.",
    ]
    return discord.Embed(
        title="🎨 Tu color de nombre",
        description="\n".join(lineas),
        color=0xF1C40F,
    )


class Selector(discord.ui.View):
    def __init__(self, conn=None) -> None:
        super().__init__(timeout=None)
        self.conn = conn

    @discord.ui.select(
        placeholder="Elegí tu color",
        custom_id="pudin_color",
        options=[
            discord.SelectOption(label="Rojo", value="🔴 Rojo", emoji="🔴"),
            discord.SelectOption(label="Naranja", value="🟠 Naranja", emoji="🟠"),
            discord.SelectOption(label="Verde", value="🟢 Verde", emoji="🟢"),
            discord.SelectOption(label="Celeste", value="🔵 Celeste", emoji="🔵"),
            discord.SelectOption(label="Violeta", value="🟣 Violeta", emoji="🟣"),
            discord.SelectOption(label="Rosa", value="🌸 Rosa", emoji="🌸"),
            discord.SelectOption(label="Sin color", value="ninguno", emoji="⚪"),
        ],
    )
    async def elegir(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        miembro = interaction.user
        if not es_donador(miembro):
            await interaction.response.send_message(
                "Los colores son para 💎 Donador. Si querés el tuyo, hablá con el staff.",
                ephemeral=True,
            )
            return

        permitido, dias = puede_elegir(self.conn, miembro)
        if not permitido:
            faltan = DIAS_COLOR - dias
            await interaction.response.send_message(
                f"El color se desbloquea a los **{DIAS_COLOR} días seguidos**.\n"
                f"Llevás **{dias}** días, te faltan **{faltan}**.",
                ephemeral=True,
            )
            return

        if _rol(interaction.guild, DORADO) in miembro.roles:
            await interaction.response.send_message(
                f"Ya tenés el color exclusivo **{DORADO}**, es el máximo.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        anteriores = [rol for rol in miembro.roles if rol.name in COLORES]
        if anteriores:
            try:
                await miembro.remove_roles(*anteriores, reason="Cambio de color")
            except discord.Forbidden:
                log.error("No pude quitarle el color a %s", miembro)

        elegido = select.values[0]
        if elegido == "ninguno":
            await interaction.followup.send("Listo, te saqué el color.", ephemeral=True)
            return

        rol = _rol(interaction.guild, elegido)
        if rol is None:
            await interaction.followup.send(
                "Ese color no existe todavia. Avisale al staff.", ephemeral=True
            )
            return
        try:
            await miembro.add_roles(rol, reason="Color elegido")
        except discord.Forbidden:
            await interaction.followup.send(
                "No pude darte el color: revisá que mi rol esté arriba de los colores.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"Listo, ahora tenés **{rol.name}**.", ephemeral=True)


async def aplicar_nivel(conn, miembro: discord.Member) -> str | None:
    """Pone o saca el dorado segun los dias seguidos. Devuelve lo que cambio."""
    guild = miembro.guild
    if guild is None:
        return None
    dorado = _rol(guild, DORADO)
    if dorado is None:
        return None
    dias = dias_seguidos(conn, miembro)
    tiene = dorado in miembro.roles

    if dias >= DIAS_DORADO and not tiene:
        otros = [rol for rol in miembro.roles if rol.name in COLORES]
        try:
            if otros:
                await miembro.remove_roles(*otros, reason="Paso al color exclusivo")
            await miembro.add_roles(dorado, reason=f"{dias} dias seguidos de donacion")
            return "dorado puesto"
        except discord.Forbidden:
            log.error("No pude dar el dorado a %s", miembro)
            return None
    if dias < DIAS_DORADO and tiene:
        try:
            await miembro.remove_roles(dorado, reason="Se corto la racha")
            return "dorado sacado"
        except discord.Forbidden:
            log.error("No pude sacarle el dorado a %s", miembro)
    return None


async def quitar_colores(miembro: discord.Member) -> None:
    """Se usa cuando vence la donacion."""
    puestos = [rol for rol in miembro.roles if rol.name in COLORES or rol.name == DORADO]
    if not puestos:
        return
    try:
        await miembro.remove_roles(*puestos, reason="Donacion vencida")
    except discord.Forbidden:
        log.error("No pude quitar los colores a %s", miembro)
