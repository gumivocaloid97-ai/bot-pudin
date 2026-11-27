"""Colores de nombre para donadores."""

from __future__ import annotations

import logging

import discord

log = logging.getLogger("pudin")

COLORES = ("🔴 Rojo", "🟠 Naranja", "🟢 Verde", "🔵 Celeste", "🟣 Violeta", "🌸 Rosa")


def es_donador(miembro: discord.abc.User) -> bool:
    permisos = getattr(miembro, "guild_permissions", None)
    if permisos is not None and permisos.administrator:
        return True
    return any("donador" in rol.name.lower() for rol in getattr(miembro, "roles", ()))


def _rol(guild: discord.Guild, nombre: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=nombre)


def embed_panel() -> discord.Embed:
    return discord.Embed(
        title="🎨 Color de nombre",
        description=(
            "Elegí el color con el que querés aparecer en el servidor.\n\n"
            "Es un beneficio de **💎 Donador**.\n"
            "Podés cambiarlo las veces que quieras."
        ),
        color=0xF1C40F,
    )


class Selector(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

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


async def quitar_colores(miembro: discord.Member) -> None:
    """Se usa cuando vence la donacion."""
    puestos = [rol for rol in miembro.roles if rol.name in COLORES]
    if not puestos:
        return
    try:
        await miembro.remove_roles(*puestos, reason="Donacion vencida")
    except discord.Forbidden:
        log.error("No pude quitar los colores a %s", miembro)
