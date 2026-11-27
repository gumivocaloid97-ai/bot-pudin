"""Bot de la Comunidad Oficial de los Pudines.

- Asigna "Los pudins" a cada miembro nuevo y lo saluda en #bienvenida.
- Da XP por actividad (mensajes y voz), con niveles y recompensas de rol.
- Comandos: /nivel y /top.
"""

import asyncio
import datetime
import logging
import unicodedata
import time
import os
import random
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

import actualizar
import musica
import niveles
import salud

GUILD_ID = 1575699459680112721
SECTA_ID = 776821377800994826

# (circulo, nivel de XP minimo, dias minimos en el servidor)
CIRCULOS = [
    ("Ⅰ・Limbo", 1, 3),
    ("Ⅱ・Lujuria", 3, 7),
    ("Ⅲ・Gula", 5, 14),
    ("Ⅳ・Avaricia", 7, 21),
    ("Ⅴ・Ira", 9, 30),
    ("Ⅵ・Herejía", 12, 45),
    ("Ⅶ・Violencia", 15, 60),
    ("Ⅷ・Fraude", 18, 90),
    ("Ⅸ・Traición", 22, 120),
]
ROL_ENTRADA = 1575699459680112723  # Los pudins
CANAL_BIENVENIDA = 1575724591811399690
CANAL_GENERAL = 1575699461777260645

XP_MENSAJE_MIN = 15
XP_MENSAJE_MAX = 25
ENFRIAMIENTO_MENSAJE = 60  # segundos entre mensajes que dan XP
XP_VOZ_POR_MINUTO = 10
MINIMO_EN_VOZ = 2  # no dar XP por estar solo en un canal

RECOMPENSAS = {5: 1575724469954027682}  # nivel -> rol (Pudin Fiel)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("pudin")


def leer_token() -> str:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if token:
        return token
    for ruta in (Path(__file__).with_name("token.txt"), Path.home() / ".discord_token"):
        if ruta.exists():
            return ruta.read_text(encoding="utf-8").strip()
    raise SystemExit("Falta el token: escribilo en token.txt junto a este archivo")


intents = discord.Intents.none()
intents.guilds = True
intents.members = True
intents.messages = True
intents.voice_states = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
db = niveles.conectar()


async def aplicar_recompensas(member: discord.Member, nivel_anterior: int, nivel_nuevo: int) -> None:
    for nivel_requerido, rol_id in sorted(RECOMPENSAS.items()):
        if not (nivel_anterior < nivel_requerido <= nivel_nuevo):
            continue
        rol = member.guild.get_role(rol_id)
        if rol is None or rol in member.roles:
            continue
        try:
            await member.add_roles(rol, reason=f"Recompensa por nivel {nivel_requerido}")
        except discord.Forbidden:
            log.error("Sin permisos para dar %s a %s", rol.name, member)
            continue
        log.info("Recompensa %s entregada a %s (nivel %s)", rol.name, member, nivel_requerido)
        canal = member.guild.get_channel(CANAL_GENERAL)
        if canal:
            await canal.send(
                f"{member.mention} llego al nivel **{nivel_requerido}** y desbloqueo el rol **{rol.name}**.",
                allowed_mentions=discord.AllowedMentions(users=True),
            )


@tasks.loop(minutes=30)
async def revisar_actualizaciones() -> None:
    if not await asyncio.to_thread(actualizar.buscar):
        return
    log.info("Actualizacion aplicada: reiniciando el bot")
    for rep in reproductores.values():
        rep.guardar_estado()
    await client.close()
    actualizar.reiniciar()


@client.event
async def on_ready() -> None:
    log.info("Conectado como %s (%s)", client.user, client.user.id)
    for servidor in client.guilds:
        log.info("Servidor: %s | miembros: %s", servidor.name, servidor.member_count)

    for servidor in client.guilds:
        try:
            tree.copy_global_to(guild=servidor)
            comandos = await tree.sync(guild=servidor)
            log.info("Comandos sincronizados en %s: %s", servidor.name, [c.name for c in comandos])
        except Exception as error:
            log.error("No pude registrar comandos en %s: %s", servidor.name, error)
    if False:
        log.error("Sin permisos para registrar comandos (falta el scope applications.commands)")

    musica.verificar_ffmpeg()
    musica.verificar_motor_js()
    try:
        from importlib.metadata import version

        import davey  # noqa: F401

        log.info("Soporte de voz DAVE: OK (davey %s)", version("davey"))
    except Exception as error:
        log.warning("davey no disponible: la voz puede fallar (%s)", error)

    if not tarea_voz.is_running():
        tarea_voz.start()
    if not tarea_circulos.is_running():
        tarea_circulos.start()
    if not revisar_actualizaciones.is_running():
        revisar_actualizaciones.start()

    for servidor in client.guilds:
        try:
            if await reproductor_de(servidor).restaurar(servidor):
                log.info("Musica retomada en %s", servidor.name)
        except Exception as error:
            log.warning("No pude retomar la musica en %s: %s", servidor.name, error)


@client.event
async def on_voice_state_update(
    member: discord.Member,
    antes: discord.VoiceState,
    despues: discord.VoiceState,
) -> None:
    if client.user is None or member.id != client.user.id:
        return
    rep = reproductores.get(member.guild.id)
    if rep is None or rep.canal_voz is None:
        return
    if despues.channel is not None and despues.channel.id == rep.canal_voz.id:
        return
    if rep.actual is None and not rep.cola:
        return
    ahora = time.monotonic()
    if ahora - _ultima_reconexion.get(member.guild.id, 0.0) < 30.0:
        return
    _ultima_reconexion[member.guild.id] = ahora
    log.info("Me movieron o me sacaron del canal de voz: vuelvo a %s", rep.canal_voz)
    client.loop.create_task(rep.reconectar())


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKC", texto).lower()


def canal_bienvenida(guild: discord.Guild) -> discord.abc.Messageable | None:
    if guild.id == GUILD_ID:
        canal = guild.get_channel(CANAL_BIENVENIDA)
        if canal is not None:
            return canal
    for canal in guild.text_channels:
        nombre = _normalizar(canal.name)
        if "bienvenid" in nombre or "welcome" in nombre:
            return canal
    return None


def rol_entrada(guild: discord.Guild) -> discord.Role | None:
    if guild.id == GUILD_ID:
        rol = guild.get_role(ROL_ENTRADA)
        if rol is not None:
            return rol
    for buscado in ("aspirante", "ignavi", "miembro", "nuevo", "iniciado"):
        for rol in guild.roles:
            if buscado in _normalizar(rol.name):
                return rol
    # ultimo recurso: el rol que tiene la mayoria de los miembros
    humanos = [m for m in guild.members if not m.bot]
    if humanos:
        candidatos = [r for r in guild.roles if not r.managed and not r.is_default()]
        if candidatos:
            popular = max(candidatos, key=lambda r: len(r.members))
            if len(popular.members) >= len(humanos) * 0.5:
                return popular
    return None


def _nombres_circulos() -> list[str]:
    return [nombre for nombre, _, _ in CIRCULOS]


async def aplicar_circulo(member: discord.Member) -> None:
    """Asciende de circulo segun actividad y antiguedad. Nunca baja a nadie."""
    guild = member.guild
    if guild.id != SECTA_ID or member.bot:
        return
    nombres = _nombres_circulos()
    por_nombre = {r.name: r for r in guild.roles if r.name in nombres}
    if not por_nombre:
        return

    _, nivel_xp = niveles.fila(db, guild.id, member.id)
    dias = (discord.utils.utcnow() - member.joined_at).days if member.joined_at else 0
    ganado = None
    for nombre, nivel_min, dias_min in CIRCULOS:
        if nivel_xp >= nivel_min and dias >= dias_min:
            ganado = nombre
    if ganado is None:
        return

    actuales = [r for r in member.roles if r.name in por_nombre]
    if actuales:
        mejor = max(actuales, key=lambda r: nombres.index(r.name))
        if nombres.index(mejor.name) > nombres.index(ganado):
            ganado = mejor.name

    sobrantes = [r for r in actuales if r.name != ganado]
    try:
        if sobrantes:
            await member.remove_roles(*sobrantes, reason="Ascenso de circulo")
        if por_nombre[ganado] not in member.roles:
            await member.add_roles(por_nombre[ganado], reason=f"Ascenso a {ganado}")
            log.info("%s asciende a %s", member, ganado)
    except discord.Forbidden:
        log.error("Sin permisos para cambiar el circulo de %s", member)


@tasks.loop(hours=6)
async def tarea_circulos() -> None:
    guild = client.get_guild(SECTA_ID)
    if guild is None:
        return
    for member in guild.members:
        await aplicar_circulo(member)
        await asyncio.sleep(0.25)


@tarea_circulos.before_loop
async def antes_de_circulos() -> None:
    await client.wait_until_ready()


@client.event
async def on_member_join(member: discord.Member) -> None:
    if member.bot:
        return

    guild = member.guild
    rol = rol_entrada(guild)
    if rol is not None and rol not in member.roles:
        try:
            await member.add_roles(rol, reason="Rol de entrada automatico")
            log.info("Rol %s asignado a %s en %s", rol.name, member, guild.name)
        except discord.Forbidden:
            log.error("Sin permisos para asignar el rol a %s", member)

    if not niveles.reclamar_bienvenida(db, guild.id, member.id):
        log.info("Bienvenida repetida de %s, la salteo", member)
        return

    await aplicar_circulo(member)

    canal = canal_bienvenida(guild)
    if canal is None:
        return

    general = guild.get_channel(CANAL_GENERAL) if guild.id == GUILD_ID else None
    embed = discord.Embed(
        title=f"Bienvenido a {guild.name}",
        description=f"{member.mention} acaba de entrar.",
        color=0xF1C40F,
    )
    embed.add_field(name="Tu rol", value=f"**{rol.name if rol else 'Sin rol'}**", inline=True)
    if general is not None:
        embed.add_field(name="Empeza por aca", value=general.mention, inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    try:
        await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
    except discord.Forbidden:
        log.error("Sin permisos para escribir en %s", canal.name)


@client.event
async def on_message(message: discord.Message) -> None:
    if message.guild is None:
        return
    if message.author.bot:
        return
    if not niveles.puede_ganar_por_mensaje(
        db, message.guild.id, message.author.id, ENFRIAMIENTO_MENSAJE
    ):
        return

    anterior, nuevo, _ = niveles.sumar_xp(
        db,
        message.guild.id,
        message.author.id,
        random.randint(XP_MENSAJE_MIN, XP_MENSAJE_MAX),
    )
    if nuevo > anterior:
        log.info("%s subio a nivel %s", message.author, nuevo)
        await aplicar_recompensas(message.author, anterior, nuevo)
        await aplicar_circulo(message.author)


@tasks.loop(minutes=1)
async def tarea_voz() -> None:
    for guild in client.guilds:
        await _voz_del_servidor(guild)


async def _voz_del_servidor(guild: discord.Guild) -> None:
    for canal in guild.voice_channels:
        if guild.afk_channel and canal.id == guild.afk_channel.id:
            continue
        humanos = [m for m in canal.members if not m.bot]
        if len(humanos) < MINIMO_EN_VOZ:
            continue
        for miembro in humanos:
            if miembro.voice.self_deaf or miembro.voice.deaf:
                continue
            anterior, nuevo, _ = niveles.sumar_xp(
                db, guild.id, miembro.id, XP_VOZ_POR_MINUTO
            )
            if nuevo > anterior:
                log.info("%s subio a nivel %s (voz)", miembro, nuevo)
                await aplicar_recompensas(miembro, anterior, nuevo)
                await aplicar_circulo(miembro)


@tarea_voz.before_loop
async def antes_de_voz() -> None:
    await client.wait_until_ready()


@tree.command(name="version", description="Muestra que version del bot esta corriendo")
async def comando_version(interaction: discord.Interaction) -> None:
    archivo = Path(__file__).with_name("version.txt")
    texto = archivo.read_text(encoding="utf-8").strip() if archivo.exists() else "sin version"
    embed = discord.Embed(title="Bot Pudin v2", description=f"Version **{texto}**", color=0xF1C40F)
    embed.set_footer(text="Se actualiza sola desde GitHub al arrancar")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="nivel", description="Muestra tu nivel, tu XP y tu puesto en el servidor")
@app_commands.describe(usuario="Consultar el nivel de otra persona")
async def comando_nivel(interaction: discord.Interaction, usuario: discord.Member | None = None) -> None:
    objetivo = usuario or interaction.user
    guild_id = interaction.guild.id
    xp_total, nivel = niveles.fila(db, guild_id, objetivo.id)
    dentro = niveles.nivel_desde_xp(xp_total)[1]
    necesario = niveles.xp_para_nivel(nivel)
    puesto = niveles.puesto(db, guild_id, objetivo.id)

    lleno = int(12 * dentro / necesario)
    barra = "#" * lleno + "-" * (12 - lleno)

    embed = discord.Embed(
        title=f"Nivel de {objetivo.display_name}",
        color=objetivo.color if getattr(objetivo, "color", None) else 0xF1C40F,
    )
    embed.set_thumbnail(url=objetivo.display_avatar.url)
    embed.add_field(name="Nivel", value=f"**{nivel}**", inline=True)
    embed.add_field(name="XP total", value=f"{xp_total:,}".replace(",", "."), inline=True)
    embed.add_field(name="Puesto", value=f"#{puesto}" if puesto else "sin actividad", inline=True)
    embed.add_field(
        name=f"Progreso al nivel {nivel + 1}",
        value=f"`{barra}` {dentro}/{necesario} XP",
        inline=False,
    )
    siguiente = next((n for n in sorted(RECOMPENSAS) if n > nivel), None)
    if siguiente:
        embed.set_footer(text=f"Al nivel {siguiente} desbloqueas un rol nuevo")
    await interaction.response.send_message(embed=embed)


@tree.command(name="top", description="Los 10 miembros mas activos del servidor")
async def comando_top(interaction: discord.Interaction) -> None:
    filas = niveles.ranking(db, interaction.guild.id, 10)
    if not filas:
        await interaction.response.send_message("Todavia no hay actividad registrada.")
        return

    lineas = []
    medallas = {1: "1.", 2: "2.", 3: "3."}
    for posicion, (user_id, xp, nivel) in enumerate(filas, start=1):
        miembro = interaction.guild.get_member(user_id)
        nombre = miembro.display_name if miembro else f"<@{user_id}>"
        prefijo = medallas.get(posicion, f"{posicion}.")
        lineas.append(f"{prefijo} **{nombre}** - nivel {nivel} - {xp:,} XP".replace(",", "."))

    embed = discord.Embed(
        title="Ranking de actividad",
        description="\n".join(lineas),
        color=0xF1C40F,
    )
    await interaction.response.send_message(embed=embed)


# ---------- musica ----------
reproductores: dict[int, musica.Reproductor] = {}
_ultima_reconexion: dict[int, float] = {}


def reproductor_de(guild: discord.Guild) -> musica.Reproductor:
    if guild.id not in reproductores:
        reproductores[guild.id] = musica.Reproductor(client)
    return reproductores[guild.id]


@tree.command(name="panel", description="Fija este canal para la tarjeta de musica")
@app_commands.default_permissions(manage_guild=True)
async def comando_panel(interaction: discord.Interaction) -> None:
    rep = reproductor_de(interaction.guild)
    rep.canal_texto = interaction.channel
    rep.panel = None
    rep.panel_donadores = None
    musica.guardar_canal_panel(interaction.guild.id, interaction.channel.id)
    await interaction.response.send_message(
        f"Listo. La tarjeta de musica va a aparecer en {interaction.channel.mention}, "
        "sin importar en que sala de voz estes.",
        ephemeral=True,
    )
    if rep.actual is not None:
        await rep._mostrar_panel()


@tree.command(name="play", description="Reproduce una cancion, un enlace o una lista")
@app_commands.describe(consulta="Nombre de la cancion, enlace de video o enlace de lista")
async def comando_play(interaction: discord.Interaction, consulta: str) -> None:
    if interaction.user.voice is None or interaction.user.voice.channel is None:
        await interaction.response.send_message("Primero entra a un canal de voz.", ephemeral=True)
        return
    await interaction.response.defer()
    rep = reproductor_de(interaction.guild)
    try:
        await rep.asegurar_conexion(interaction.user.voice.channel)
        pistas = await rep.buscar(consulta)
        if not pistas:
            await interaction.followup.send("No encontre nada con eso.", ephemeral=True)
            return
        await rep.encolar(pistas, interaction.channel, interaction.user.display_name)
    except Exception as error:
        if musica.es_error_de_verificacion(error):
            await interaction.followup.send(
                "YouTube pidio verificacion de cuenta.\n"
                "Exporta tus cookies de YouTube y guardalas como `cookies.txt` "
                "en la carpeta del bot, al lado de `Iniciar Bot.bat`. "
                "Despues reinicia el bot.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"No pude reproducir eso: `{error}`", ephemeral=True)
        return

    if len(pistas) > 1:
        texto = f"➕ {len(pistas)} temas agregados a la cola"
    else:
        texto = f"➕ {pistas[0].titulo}"
    await interaction.followup.send(texto, ephemeral=True)


@tree.command(name="cola", description="Muestra lo que esta sonando y lo que sigue")
async def comando_cola(interaction: discord.Interaction) -> None:
    rep = reproductor_de(interaction.guild)
    if not rep.actual and not rep.cola:
        await interaction.response.send_message("No hay nada reproduciendose.", ephemeral=True)
        return
    lineas = []
    if rep.actual:
        lineas.append(f"**Sonando:** {rep.actual.titulo}")
    if rep.cola:
        lineas.append("**Sigue:**")
        for i, pista in enumerate(list(rep.cola)[:10], start=1):
            lineas.append(f"{i}. {pista.titulo}")
        if len(rep.cola) > 10:
            lineas.append(f"… y {len(rep.cola) - 10} mas")
    await interaction.response.send_message("\n".join(lineas))


@tree.command(name="pausa", description="Pausa la musica, o la reanuda si estaba en pausa")
async def comando_pausa(interaction: discord.Interaction) -> None:
    rep = reproductor_de(interaction.guild)
    await interaction.response.send_message(await rep.alternar_pausa(), ephemeral=True, delete_after=4)


@tree.command(name="saltar", description="Pasa a la siguiente cancion de la cola")
async def comando_saltar(interaction: discord.Interaction) -> None:
    rep = reproductor_de(interaction.guild)
    anterior = await rep.saltar()
    texto = f"Saltada: **{anterior}**" if anterior else "No hay nada sonando."
    await interaction.response.send_message(texto)


@tree.command(name="parar", description="Detiene la musica y vacia la cola")
async def comando_parar(interaction: discord.Interaction) -> None:
    rep = reproductor_de(interaction.guild)
    await rep.detener()
    await interaction.response.send_message("Musica detenida y cola vaciada.")


@tree.command(name="salir", description="Saca al bot del canal de voz")
async def comando_salir(interaction: discord.Interaction) -> None:
    rep = reproductor_de(interaction.guild)
    await rep.desconectar()
    await interaction.response.send_message("Listo, sali del canal de voz.")


# ---------- moderacion ----------
def tiene(interaction: discord.Interaction, **permisos: bool) -> bool:
    p = interaction.user.guild_permissions
    return p.administrator or all(getattr(p, nombre, False) for nombre, valor in permisos.items() if valor)


async def negar(interaction: discord.Interaction, permiso: str) -> None:
    await interaction.response.send_message(
        f"Necesitas el permiso **{permiso}** para usar esto.", ephemeral=True
    )


@tree.command(name="borrar", description="Borra los ultimos mensajes del canal")
@app_commands.describe(cantidad="Cuantos mensajes borrar (1 a 100)")
@app_commands.default_permissions(manage_messages=True)
async def comando_borrar(interaction: discord.Interaction, cantidad: app_commands.Range[int, 1, 100]) -> None:
    if not tiene(interaction, manage_messages=True):
        await negar(interaction, "Gestionar mensajes")
        return
    await interaction.response.defer(ephemeral=True)
    borrados = await interaction.channel.purge(limit=cantidad)
    await interaction.followup.send(f"Borre {len(borrados)} mensajes.", ephemeral=True)


@tree.command(name="expulsar", description="Expulsa a un miembro del servidor")
@app_commands.describe(usuario="A quien expulsar", motivo="Por que")
@app_commands.default_permissions(kick_members=True)
async def comando_expulsar(interaction: discord.Interaction, usuario: discord.Member, motivo: str = "sin motivo") -> None:
    if not tiene(interaction, kick_members=True):
        await negar(interaction, "Expulsar miembros")
        return
    if usuario.id == interaction.user.id:
        await interaction.response.send_message("No te puedo expulsar a vos mismo.", ephemeral=True)
        return
    try:
        await usuario.kick(reason=f"{interaction.user}: {motivo}")
    except discord.Forbidden:
        await interaction.response.send_message("No pude expulsarlo: su rol esta por encima del mio.", ephemeral=True)
        return
    await interaction.response.send_message(f"Expulsado **{usuario}**. Motivo: {motivo}")


@tree.command(name="banear", description="Banea a un miembro del servidor")
@app_commands.describe(usuario="A quien banear", motivo="Por que")
@app_commands.default_permissions(ban_members=True)
async def comando_banear(interaction: discord.Interaction, usuario: discord.Member, motivo: str = "sin motivo") -> None:
    if not tiene(interaction, ban_members=True):
        await negar(interaction, "Banear miembros")
        return
    if usuario.id == interaction.user.id:
        await interaction.response.send_message("No te puedo banear a vos mismo.", ephemeral=True)
        return
    try:
        await usuario.ban(reason=f"{interaction.user}: {motivo}", delete_message_days=0)
    except discord.Forbidden:
        await interaction.response.send_message("No pude banearlo: su rol esta por encima del mio.", ephemeral=True)
        return
    await interaction.response.send_message(f"Baneado **{usuario}**. Motivo: {motivo}")


@tree.command(name="silenciar", description="Silencia temporalmente a un miembro")
@app_commands.describe(usuario="A quien silenciar", minutos="Duracion en minutos", motivo="Por que")
@app_commands.default_permissions(moderate_members=True)
async def comando_silenciar(
    interaction: discord.Interaction,
    usuario: discord.Member,
    minutos: app_commands.Range[int, 1, 10080] = 10,
    motivo: str = "sin motivo",
) -> None:
    if not tiene(interaction, moderate_members=True):
        await negar(interaction, "Silenciar miembros")
        return
    try:
        await usuario.timeout(datetime.timedelta(minutes=minutos), reason=f"{interaction.user}: {motivo}")
    except discord.Forbidden:
        await interaction.response.send_message("No pude silenciarlo: su rol esta por encima del mio.", ephemeral=True)
        return
    await interaction.response.send_message(f"**{usuario}** silenciado por {minutos} minutos. Motivo: {motivo}")


# ---------- utilidad ----------
@tree.command(name="ping", description="Muestra la latencia del bot")
async def comando_ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(f"Latencia: **{round(client.latency * 1000)} ms**")


@tree.command(name="servidor", description="Informacion del servidor")
async def comando_servidor(interaction: discord.Interaction) -> None:
    g = interaction.guild
    embed = discord.Embed(title=g.name, color=0xF1C40F)
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="Miembros", value=g.member_count, inline=True)
    embed.add_field(name="Canales", value=len(g.channels), inline=True)
    embed.add_field(name="Roles", value=len(g.roles), inline=True)
    embed.add_field(name="Dueño", value=f"<@{g.owner_id}>", inline=True)
    embed.add_field(name="Creado", value=g.created_at.strftime("%d/%m/%Y"), inline=True)
    await interaction.response.send_message(embed=embed)


@tree.command(name="usuario", description="Informacion de un miembro")
@app_commands.describe(usuario="De quien ver la ficha")
async def comando_usuario(interaction: discord.Interaction, usuario: discord.Member | None = None) -> None:
    m = usuario or interaction.user
    xp_total, nivel = niveles.fila(db, interaction.guild.id, m.id)
    embed = discord.Embed(title=m.display_name, color=m.color or 0xF1C40F)
    embed.set_thumbnail(url=m.display_avatar.url)
    embed.add_field(name="Se unio", value=m.joined_at.strftime("%d/%m/%Y") if m.joined_at else "-", inline=True)
    embed.add_field(name="Nivel", value=nivel, inline=True)
    embed.add_field(name="XP", value=f"{xp_total:,}".replace(",", "."), inline=True)
    embed.add_field(
        name="Roles",
        value=", ".join(r.mention for r in m.roles if r.name != "@everyone") or "ninguno",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="ayuda", description="Lista todo lo que sabe hacer el bot")
async def comando_ayuda(interaction: discord.Interaction) -> None:
    grupos = {
        "Niveles": "/nivel · /top",
        "Musica": "/play · /cola · /pausa · /saltar · /parar · /salir · /panel",
        "Moderacion": "/borrar · /expulsar · /banear · /silenciar",
        "Utilidad": "/ping · /servidor · /usuario · /ayuda",
    }
    embed = discord.Embed(title="Bot Pudin v.2", description="Todo lo que puedo hacer", color=0xF1C40F)
    for nombre, lista in grupos.items():
        embed.add_field(name=nombre, value=lista, inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="probar", description="Prueba de audio: reproduce un tono de 5 segundos")
async def comando_probar(interaction: discord.Interaction) -> None:
    if interaction.user.voice is None or interaction.user.voice.channel is None:
        await interaction.response.send_message("Primero entra a un canal de voz.", ephemeral=True)
        return
    await interaction.response.defer()
    rep = reproductor_de(interaction.guild)
    await rep.asegurar_conexion(interaction.user.voice.channel)
    await rep.detener()
    await rep.tono(5)
    await interaction.followup.send("Tono enviado. Se escucho algo?")


if __name__ == "__main__":
    if actualizar.buscar():
        actualizar.reiniciar()
    salud.iniciar()
    client.run(leer_token(), log_handler=None)
