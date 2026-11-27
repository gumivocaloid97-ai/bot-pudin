"""Tickets de donacion: un canal privado por persona."""

from __future__ import annotations

import asyncio
import logging

import discord

log = logging.getLogger("pudin")

ROL_STAFF = 1575815434530324521  # 🛡️ Moderador Pudin


def _propietario(canal: discord.abc.GuildChannel) -> int | None:
    tema = getattr(canal, "topic", None) or ""
    if "ticket|" not in tema:
        return None
    try:
        return int(tema.split("ticket|")[1].split()[0])
    except (IndexError, ValueError):
        return None


def _es_staff(miembro: discord.Member) -> bool:
    if miembro.guild_permissions.administrator:
        return True
    return any(rol.id == ROL_STAFF for rol in miembro.roles)


class CerrarTicket(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Cerrar ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="pudin_ticket_cerrar",
    )
    async def cerrar(self, interaction: discord.Interaction, boton: discord.ui.Button) -> None:
        canal = interaction.channel
        dueno = _propietario(canal)
        if interaction.user.id != dueno and not _es_staff(interaction.user):
            await interaction.response.send_message(
                "Solo quien abrio el ticket o el staff puede cerrarlo.", ephemeral=True
            )
            return
        await interaction.response.send_message("Cerrando el ticket en 5 segundos...")
        await asyncio.sleep(5)
        try:
            await canal.delete(reason=f"Ticket cerrado por {interaction.user}")
        except discord.HTTPException as error:
            log.warning("No pude borrar el ticket %s: %s", canal, error)


class PanelTicket(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Quiero donar",
        emoji="🎫",
        style=discord.ButtonStyle.success,
        custom_id="pudin_ticket_abrir",
    )
    async def abrir(self, interaction: discord.Interaction, boton: discord.ui.Button) -> None:
        guild = interaction.guild
        if guild is None:
            return
        nombre = "ticket-" + "".join(
            letra for letra in interaction.user.name.lower() if letra.isalnum() or letra in "-_"
        )
        nombre = nombre[:90]
        existente = discord.utils.get(guild.text_channels, name=nombre)
        if existente is not None:
            await interaction.response.send_message(
                f"Ya tenes un ticket abierto: {existente.mention}", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        permisos = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        staff = guild.get_role(ROL_STAFF)
        if staff is not None:
            permisos[staff] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
        try:
            canal = await guild.create_text_channel(
                nombre,
                overwrites=permisos,
                topic=f"ticket|{interaction.user.id}",
                reason="Ticket de donacion",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "No tengo permiso para crear canales. Avisale al staff.", ephemeral=True
            )
            return
        except discord.HTTPException as error:
            await interaction.followup.send(f"No pude abrir el ticket: `{error}`", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎫 Ticket de donación",
            description=(
                f"Hola {interaction.user.mention}, este canal es solo tuyo y del staff.\n\n"
                "**Contame qué necesitás:**\n"
                "• Querés ser 💎 Donador\n"
                "• Querés renovar tu mes\n"
                "• Una duda sobre los beneficios\n\n"
                "Cuando termine, tocá **Cerrar ticket**."
            ),
            color=0xF1C40F,
        )
        menciones = discord.AllowedMentions(users=True, roles=True)
        try:
            await canal.send(
                content=f"{interaction.user.mention} <@&{ROL_STAFF}>",
                embed=embed,
                view=CerrarTicket(),
                allowed_mentions=menciones,
            )
        except discord.HTTPException as error:
            log.warning("No pude escribir en el ticket: %s", error)
        await interaction.followup.send(f"Listo, te abrí {canal.mention}", ephemeral=True)


def embed_panel() -> discord.Embed:
    return discord.Embed(
        title="💎 Donaciones",
        description=(
            "El servidor se mantiene con las donaciones de la gente que lo banca.\n\n"
            "**💎 Donador — 1 mes**\n"
            "• Canal 💎・donadores y 🔊・donadores\n"
            "• Radio Pudin y el panel completo\n"
            "• Apodo con emoji\n"
            "• Sorteos exclusivos\n\n"
            "**🎨 Color de nombre — 2 meses seguidos**\n"
            "• Elegís el color con el que aparecés\n\n"
            "**👑 Color dorado — 5 meses seguidos**\n"
            "• El color exclusivo, solo para los que no cortan\n\n"
            "Tocá el botón y te abro un canal privado para hablar."
        ),
        color=0xF1C40F,
    )
