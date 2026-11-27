"""Reproduccion de audio en canales de voz, con cola y panel de control."""

import asyncio
import json
import unicodedata
import logging
import os
import shlex
import shutil
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import discord
import yt_dlp

log = logging.getLogger("pudin.musica")

# yt-dlp necesita un motor de JavaScript (deno) para descifrar YouTube.
# En el paquete portable viene en la carpeta bin/, al lado de este archivo.
_CARPETA_BIN = Path(__file__).resolve().parent / "bin"
if _CARPETA_BIN.is_dir():
    os.environ["PATH"] = str(_CARPETA_BIN) + os.pathsep + os.environ.get("PATH", "")

CARPETA = Path(tempfile.gettempdir()) / "pudin_musica"
CARPETA.mkdir(exist_ok=True)

MAX_PISTAS = 50

# Servidores donde los botones son exclusivos de 💎 Donador (para monetizar).
# En el resto, los botones los ve y los usa cualquiera.
GUILDS_PRIVADOS = {1575699459680112721}

# Si el usuario exporta sus cookies de YouTube aca, yt-dlp las usa automaticamente.
COOKIES = Path(__file__).resolve().parent / "cookies.txt"

# Canal fijo donde vive la tarjeta de musica (se configura con /panel).
ARCHIVO_PANEL = Path(__file__).resolve().parent / "panel.txt"

# Ids de las tarjetas publicadas, para editarlas en vez de duplicarlas al reiniciar.
ARCHIVO_PANELES = Path(__file__).resolve().parent / "paneles.json"


ARCHIVO_ESTADO = Path(__file__).resolve().parent / "estado_reproduccion.json"


def _leer_estado() -> dict:
    try:
        return json.loads(ARCHIVO_ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar_estado(datos: dict) -> None:
    try:
        ARCHIVO_ESTADO.write_text(json.dumps(datos), encoding="utf-8")
    except OSError:
        pass


def _olvidar_estado(guild_id: int) -> None:
    datos = _leer_estado()
    if datos.pop(str(guild_id), None) is not None:
        _guardar_estado(datos)


def _leer_paneles() -> dict:
    try:
        return json.loads(ARCHIVO_PANELES.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar_paneles(datos: dict) -> None:
    try:
        ARCHIVO_PANELES.write_text(json.dumps(datos), encoding="utf-8")
    except OSError:
        pass

OPCIONES_BUSQUEDA = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": "in_playlist",
    "noplaylist": False,
}

OPCIONES_DESCARGA = {
    "format": "bestaudio/best/b",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "outtmpl": str(CARPETA / "%(id)s.%(ext)s"),
}


@dataclass
class Pista:
    titulo: str
    consulta: str
    archivo: Path | None = None
    pedido_por: str = ""
    url_directa: str | None = None
    cabeceras: dict = field(default_factory=dict)
    duracion: float | None = None
    desde: float = 0.0


def mmss(segundos: float | None) -> str:
    if segundos is None or segundos < 0:
        return "--:--"
    total = int(segundos)
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    if horas:
        return f"{horas}:{minutos:02d}:{segs:02d}"
    return f"{minutos}:{segs:02d}"


def es_donador(miembro: discord.abc.User) -> bool:
    permisos = getattr(miembro, "guild_permissions", None)
    if permisos is not None and permisos.administrator:
        return True
    guild = getattr(miembro, "guild", None)
    if guild is not None and getattr(guild, "owner_id", None) == getattr(miembro, "id", None):
        return True
    roles = getattr(miembro, "roles", ())
    return any("donador" in rol.name.lower() for rol in roles)


def canal_donadores(guild: discord.Guild | None) -> discord.TextChannel | None:
    """Canal privado de donadores: ahi van los botones de musica."""
    if guild is None:
        return None
    for canal in guild.text_channels:
        if "donador" in canal.name.lower():
            return canal
    return None


def ruta_ffmpeg() -> str | None:
    """Busca FFmpeg en el PATH y, si no esta, en el binario que trae imageio-ffmpeg."""
    if os.environ.get("FFMPEG_PATH"):
        return os.environ["FFMPEG_PATH"]
    encontrado = shutil.which("ffmpeg")
    if encontrado:
        return encontrado
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def verificar_motor_js() -> bool:
    encontrado = shutil.which("deno") or shutil.which("node") or shutil.which("qjs")
    if encontrado:
        log.info("Motor de JavaScript: %s", encontrado)
        return True
    log.warning("Sin motor de JavaScript: YouTube puede fallar con 'format not available'.")
    return False


def verificar_ffmpeg() -> bool:
    ruta = ruta_ffmpeg()
    if ruta is None:
        log.error("FFmpeg no encontrado: la musica no va a funcionar.")
        return False
    log.info("FFmpeg: %s", ruta)
    return True


def canal_panel_guardado(guild_id: int | None) -> int | None:
    try:
        datos = json.loads(ARCHIVO_PANEL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        try:
            return int(ARCHIVO_PANEL.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
    if not isinstance(datos, dict) or guild_id is None:
        return None
    valor = datos.get(str(guild_id))
    return int(valor) if valor is not None else None


def guardar_canal_panel(guild_id: int, canal_id: int) -> None:
    try:
        try:
            datos = json.loads(ARCHIVO_PANEL.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                datos = {}
        except (OSError, ValueError):
            datos = {}
        datos[str(guild_id)] = str(canal_id)
        ARCHIVO_PANEL.write_text(json.dumps(datos), encoding="utf-8")
    except OSError as error:
        log.warning("No pude guardar el canal del panel: %s", error)


def es_error_de_verificacion(error: Exception) -> bool:
    texto = str(error).lower()
    return "not a bot" in texto or "sign in to confirm" in texto or "confirm you" in texto


def es_error_reintentable(error: Exception) -> bool:
    texto = str(error).lower()
    return (
        es_error_de_verificacion(error)
        or "requested format is not available" in texto
        or "cookie" in texto
        or "could not find" in texto
        or "failed to decrypt" in texto
        or "page needs to be reloaded" in texto
    )


def navegadores_disponibles() -> list[str]:
    """Solo intenta leer cookies de navegadores que estan instalados de verdad."""
    appdata = Path(os.environ.get("APPDATA", ""))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidatos = {
        "firefox": appdata / "Mozilla" / "Firefox" / "Profiles",
        "edge": local / "Microsoft" / "Edge" / "User Data",
        "chrome": local / "Google" / "Chrome" / "User Data",
    }
    return [nombre for nombre, ruta in candidatos.items() if ruta.is_dir()]


def variantes_descarga() -> list[dict]:
    """Formas de pedirle el audio a YouTube, de la mas simple a la mas completa."""
    variantes: list[dict] = []
    if COOKIES.exists():
        variantes.append({"cookiefile": str(COOKIES)})
    variantes.append({})
    for cliente in ("tv", "web_safari", "mweb"):
        variantes.append({"extractor_args": {"youtube": {"player_client": [cliente]}}})
    for navegador in navegadores_disponibles():
        variantes.append({"cookiesfrombrowser": (navegador,)})
    return variantes


def es_lista(consulta: str) -> bool:
    return "list=" in consulta or "/playlist" in consulta


class SaltoSelect(discord.ui.Select):
    """Desplegable para saltar a un momento de la cancion."""

    def __init__(self, panel: "Panel") -> None:
        self.panel = panel
        self.reproductor = panel.reproductor
        super().__init__(
            placeholder="⏱️ Ir a un momento",
            custom_id="pudin_salto",
            row=1,
            options=[discord.SelectOption(label="Sin reproduccion", value="0")],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.panel.puede_usar(interaction):
            return
        await interaction.response.defer()
        await self.reproductor.saltar_a(float(self.values[0]))
        await self.panel.refrescar(interaction)


class VolumenSelect(discord.ui.Select):
    """Desplegable de volumen."""

    def __init__(self, panel: "Panel") -> None:
        self.panel = panel
        self.reproductor = panel.reproductor
        super().__init__(
            placeholder="🔊 Volumen",
            custom_id="pudin_volumen",
            row=2,
            options=[
                discord.SelectOption(label="Silencio", value="0", emoji="🔇"),
                discord.SelectOption(label="25%", value="0.25"),
                discord.SelectOption(label="50%", value="0.5"),
                discord.SelectOption(label="75%", value="0.75"),
                discord.SelectOption(label="100%", value="1"),
                discord.SelectOption(label="125%", value="1.25"),
                discord.SelectOption(label="150%", value="1.5"),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.panel.puede_usar(interaction):
            return
        await interaction.response.defer()
        self.reproductor.fijar_volumen(float(self.values[0]))
        await self.reproductor.actualizar_panel()
        await self.panel.refrescar(interaction)


class SaltoBoton(discord.ui.Button):
    """Cada boton de la fila es un punto de la cancion."""

    def __init__(self, panel: "Panel", indice: int) -> None:
        self.panel = panel
        self.indice = indice
        self.posicion = 0.0
        super().__init__(
            label="--:--",
            style=discord.ButtonStyle.secondary,
            custom_id=f"pudin_pos{indice}",
            row=4,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.panel.puede_usar(interaction):
            return
        await interaction.response.defer()
        await self.panel.reproductor.saltar_a(self.posicion)
        await self.panel.refrescar(interaction)


class Panel(discord.ui.View):
    """Controles de musica."""

    def __init__(self, reproductor: "Reproductor", efimero: bool = False) -> None:
        super().__init__(timeout=None)
        self.reproductor = reproductor
        self.efimero = efimero
        self.add_item(SaltoSelect(self))
        self.add_item(VolumenSelect(self))
        self.posiciones = [SaltoBoton(self, indice) for indice in range(5)]
        for boton in self.posiciones:
            self.add_item(boton)

    async def refrescar(self, interaction: discord.Interaction) -> None:
        """Mantiene al dia el panel privado despues de cada boton."""
        if not self.efimero:
            return
        self.reproductor._ajustar_vista(self)
        try:
            await interaction.edit_original_response(
                content=self.reproductor.texto_panel(), view=self
            )
        except discord.HTTPException:
            pass

    async def puede_usar(self, interaction: discord.Interaction) -> bool:
        privado = getattr(interaction.guild, "id", None) in GUILDS_PRIVADOS
        if privado and not es_donador(interaction.user):
            await interaction.response.send_message(
                "Los botones son para 💎 Donador. Igual podes pedir temas con /play.",
                ephemeral=True,
            )
            return False
        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.response.send_message(
                "Entra a un canal de voz para usar los controles.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="pudin_pausa", row=0)
    async def pausar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.puede_usar(interaction):
            return
        await interaction.response.defer()
        await self.reproductor.alternar_pausa()
        await self.refrescar(interaction)

    @discord.ui.button(label="-30s", emoji="⏪", style=discord.ButtonStyle.secondary, custom_id="pudin_atras", row=0)
    async def atras(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.puede_usar(interaction):
            return
        await interaction.response.defer()
        await self.reproductor.mover(-30)
        await self.refrescar(interaction)

    @discord.ui.button(label="+30s", emoji="⏩", style=discord.ButtonStyle.secondary, custom_id="pudin_adelante", row=0)
    async def adelante(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.puede_usar(interaction):
            return
        await interaction.response.defer()
        await self.reproductor.mover(30)
        await self.refrescar(interaction)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="pudin_parar", row=0)
    async def parar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.puede_usar(interaction):
            return
        await interaction.response.defer()
        await self.reproductor.detener()
        await self.refrescar(interaction)

    @discord.ui.button(label="Cola", emoji="📜", style=discord.ButtonStyle.secondary, custom_id="pudin_cola", row=3)
    async def cola(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.puede_usar(interaction):
            return
        await interaction.response.send_message(self.reproductor.texto_cola(), ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="pudin_siguiente", row=3)
    async def siguiente(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self.puede_usar(interaction):
            return
        await interaction.response.defer()
        await self.reproductor.saltar()
        await self.refrescar(interaction)


class Reproductor:
    """Una instancia por servidor."""

    def __init__(self, client: discord.Client) -> None:
        self.client = client
        self.cola: deque[Pista] = deque()
        self.actual: Pista | None = None
        self.voz: discord.VoiceClient | None = None
        self.canal_voz: discord.VoiceChannel | None = None
        self.canal_texto: discord.abc.Messageable | None = None
        self.panel: discord.Message | None = None
        self.panel_donadores: discord.Message | None = None
        self.vista = Panel(self)
        self.fuente: discord.PCMVolumeTransformer | None = None
        self.volumen = 1.0
        self.inicio: float | None = None
        self.pausado_desde: float | None = None
        self._candado = asyncio.Lock()
        self._descargando = False
        self._avanzando = False
        self._avisado_cookies = False
        self._cargando = False
        self._variante_ok: dict | None = None

    async def buscar(self, consulta: str) -> list[Pista]:
        """Devuelve las pistas a encolar. Una lista de YouTube devuelve todas."""

        def _extraer() -> list[Pista]:
            with yt_dlp.YoutubeDL(OPCIONES_BUSQUEDA) as ydl:
                objetivo = consulta if consulta.startswith("http") else f"ytsearch1:{consulta}"
                info = ydl.extract_info(objetivo, download=False)

                if es_lista(consulta) and info.get("entries"):
                    pistas = []
                    for entrada in list(info["entries"])[:MAX_PISTAS]:
                        if not entrada:
                            continue
                        url = entrada.get("url") or entrada.get("webpage_url")
                        if not url:
                            continue
                        pistas.append(
                            Pista(entrada.get("title") or "Sin titulo", url,
                                  duracion=entrada.get("duration"))
                        )
                    return pistas

                if info.get("entries"):
                    info = next((e for e in info["entries"] if e), None) or {}
                url = info.get("webpage_url") or info.get("url") or consulta
                return [Pista(info.get("title") or consulta, url, duracion=info.get("duration"))]

        return await asyncio.to_thread(_extraer)

    def _orden_variantes(self) -> list[dict]:
        variantes = variantes_descarga()
        if self._variante_ok in variantes:
            variantes.remove(self._variante_ok)
            variantes.insert(0, self._variante_ok)
        return variantes

    async def descargar(self, pista: Pista) -> None:
        if pista.url_directa or (pista.archivo and pista.archivo.exists()):
            return
        ganadora: dict | None = None
        duracion: float | None = None

        def _bajar() -> tuple[str | None, Path | None, dict]:
            nonlocal ganadora, duracion
            ultimo: Exception | None = None
            for extra in self._orden_variantes():
                opciones = dict(OPCIONES_DESCARGA)
                opciones.update(extra)
                ejecutable = ruta_ffmpeg()
                if ejecutable:
                    opciones["ffmpeg_location"] = ejecutable
                try:
                    with yt_dlp.YoutubeDL(opciones) as ydl:
                        info = ydl.extract_info(pista.consulta, download=False)
                        if info.get("entries"):
                            info = info["entries"][0]
                        duracion = info.get("duration")
                        if info.get("is_live"):
                            # Una transmision en vivo nunca termina: se transmite, no se descarga.
                            return info.get("url"), None, info.get("http_headers") or {}
                        # process_ie_result evita pedir la pagina de YouTube dos veces.
                        info = ydl.process_ie_result(info, download=True)
                        ganadora = extra
                        if extra:
                            log.info("Descarga OK con la variante %s", extra)
                        return None, Path(ydl.prepare_filename(info)), {}
                except yt_dlp.utils.DownloadError as error:
                    ultimo = error
                    if not es_error_reintentable(error):
                        raise
                    log.warning("Ese intento no sirvio, pruebo otra forma (%s)", extra)
            if ultimo:
                raise ultimo
            raise RuntimeError("No pude descargar el audio")

        pista.url_directa, pista.archivo, pista.cabeceras = await asyncio.to_thread(_bajar)
        if pista.duracion is None and duracion:
            pista.duracion = duracion
        if ganadora is not None and ganadora != self._variante_ok:
            self._variante_ok = ganadora
            log.info("Recordando la variante que funciona: %s", ganadora)

    def canal_para_panel(self, por_defecto: discord.abc.Messageable) -> discord.abc.Messageable:
        """La tarjeta va siempre al canal fijado con /panel, no al canal del comando."""
        if self.canal_texto is not None:
            return self.canal_texto
        guild = getattr(por_defecto, "guild", None)
        guardado = canal_panel_guardado(getattr(guild, "id", None))
        if guardado is not None and self.client is not None:
            canal = self.client.get_channel(guardado)
            if canal is not None:
                self.canal_texto = canal
                return canal
        # sin /panel configurado: buscar un canal de texto de comandos o bot
        for clave in ("comando", "bot", "musica"):
            for canal in getattr(guild, "text_channels", []) or []:
                if clave in unicodedata.normalize("NFKC", canal.name).lower():
                    self.canal_texto = canal
                    return canal
        self.canal_texto = por_defecto
        return por_defecto

    async def encolar(self, pistas: list[Pista], canal_texto: discord.abc.Messageable,
                      autor: str) -> None:
        for pista in pistas:
            pista.pedido_por = autor
            self.cola.append(pista)
        self.canal_texto = self.canal_para_panel(canal_texto)
        if not (self.voz and (self.voz.is_playing() or self.voz.is_paused())):
            await self._avanzar()

    async def asegurar_conexion(self, canal: discord.VoiceChannel) -> discord.VoiceClient:
        # Conectar dos veces al mismo servidor invalida la sesion anterior (close 4006).
        self.canal_voz = canal
        async with self._candado:
            existente = discord.utils.get(self.client.voice_clients, guild=canal.guild)
            if existente is not None:
                if existente.is_connected() and existente.channel and existente.channel.id != canal.id:
                    await existente.move_to(canal)
                self.voz = existente
                return existente
            self.voz = await canal.connect(self_deaf=True, timeout=30.0, reconnect=True)
            return self.voz

    async def reconectar(self) -> None:
        """Vuelve al canal de voz y retoma el tema que estaba sonando."""
        if self.canal_voz is None:
            return
        pista = self.actual
        self.actual = None
        if pista is not None:
            self.cola.appendleft(pista)
        try:
            await self.asegurar_conexion(self.canal_voz)
            await self._avanzar()
        except Exception as error:
            log.error("No pude volver al canal de voz: %s", error)

    # panel

    def _transcurrido(self) -> float:
        if self.inicio is None:
            return 0.0
        fin = self.pausado_desde if self.pausado_desde is not None else time.monotonic()
        return max(0.0, fin - self.inicio)

    def _linea_progreso(self) -> str | None:
        if self.actual is None or not self.actual.duracion:
            return None
        total = self.actual.duracion
        actual = min(self._transcurrido(), total)
        tramos = 12
        lleno = int(tramos * actual / total)
        barra = "▬" * lleno + "🔘" + "▬" * max(0, tramos - lleno)
        return f"{barra} `{mmss(actual)} / {mmss(total)}`"

    def _texto_panel(self) -> str:
        if self.actual is None:
            return "🎵 **Sin reproduccion**"
        if self._cargando:
            icono = "⏳"
        elif self.voz and self.voz.is_paused():
            icono = "⏸️"
        elif self.actual.url_directa:
            icono = "🔴"
        else:
            icono = "🎵"
        lineas = [f"{icono} **{self.actual.titulo}**"]
        progreso = self._linea_progreso()
        if progreso:
            lineas.append(progreso)
        if self.actual.pedido_por:
            lineas.append(f"Pedido por {self.actual.pedido_por}")
        if self.cola:
            lineas.append(f"En cola: {len(self.cola)}")
        return "\n".join(lineas)

    def guardar_estado(self) -> None:
        """Deja anotado que suena y por donde va, para retomarlo al reiniciar."""
        if self.actual is None or self.canal_voz is None:
            return
        datos = _leer_estado()
        datos[str(self.canal_voz.guild.id)] = {
            "voz": self.canal_voz.id,
            "texto": getattr(self.canal_texto, "id", None),
            "volumen": self.volumen,
            "actual": {
                "consulta": self.actual.consulta,
                "titulo": self.actual.titulo,
                "duracion": self.actual.duracion,
                "desde": self._transcurrido(),
                "archivo": str(self.actual.archivo) if self.actual.archivo else None,
            },
            "cola": [
                {"consulta": p.consulta, "titulo": p.titulo, "duracion": p.duracion}
                for p in self.cola
            ],
        }
        _guardar_estado(datos)

    async def restaurar(self, guild: discord.Guild) -> bool:
        """Vuelve a poner lo que sonaba antes de reiniciar."""
        datos = _leer_estado().get(str(guild.id))
        if not datos:
            return False
        canal_voz = guild.get_channel(datos.get("voz") or 0)
        if canal_voz is None or not hasattr(canal_voz, "connect"):
            _olvidar_estado(guild.id)
            return False
        if not any(not miembro.bot for miembro in canal_voz.members):
            log.info("No retomo la musica en %s: el canal de voz esta vacio", guild.name)
            _olvidar_estado(guild.id)
            return False

        guardadas: list[Pista] = []
        actual = datos.get("actual") or {}
        if actual.get("consulta"):
            pista = Pista(
                actual.get("titulo") or "Sin titulo",
                actual["consulta"],
                duracion=actual.get("duracion"),
                desde=float(actual.get("desde") or 0.0),
            )
            archivo = actual.get("archivo")
            if archivo and Path(archivo).exists():
                pista.archivo = Path(archivo)
            guardadas.append(pista)
        for guardada in datos.get("cola") or []:
            if guardada.get("consulta"):
                guardadas.append(
                    Pista(guardada.get("titulo") or "Sin titulo", guardada["consulta"],
                          duracion=guardada.get("duracion"))
                )
        if not guardadas:
            _olvidar_estado(guild.id)
            return False

        self.canal_texto = guild.get_channel(datos.get("texto") or 0) or canal_voz
        self.volumen = float(datos.get("volumen") or 1.0)
        conectado = False
        for intento in range(1, 4):
            try:
                await self.asegurar_conexion(canal_voz)
                conectado = True
                break
            except Exception as error:
                log.warning(
                    "No pude entrar al canal de voz en %s (intento %s/3): %s",
                    guild.name, intento, error,
                )
                await asyncio.sleep(6)
        if not conectado:
            log.error("No retomo la musica en %s: no pude conectarme al canal", guild.name)
            return False
        self.cola.clear()
        self.cola.extend(guardadas)
        _olvidar_estado(guild.id)
        log.info("Retomo donde habia quedado: %s (%s)", guardadas[0].titulo, mmss(guardadas[0].desde))
        await self._avanzar()
        return True

    def olvidar_estado(self) -> None:
        guild = self.canal_voz.guild.id if self.canal_voz is not None else None
        if guild:
            _olvidar_estado(guild)

    def esta_sonando(self) -> bool:
        if self.voz is None or self.actual is None:
            return False
        return self.voz.is_playing() or self.voz.is_paused()

    def texto_cola(self) -> str:
        if not self.cola:
            return "La cola esta vacia."
        lineas = []
        for numero, pista in enumerate(list(self.cola)[:10], 1):
            duracion = f" `{mmss(pista.duracion)}`" if pista.duracion else ""
            lineas.append(f"{numero}. **{pista.titulo}**{duracion}")
        resto = len(self.cola) - 10
        if resto > 0:
            lineas.append(f"... y {resto} mas")
        return "\n".join(lineas)

    def fijar_volumen(self, valor: float) -> float:
        self.volumen = max(0.0, min(1.5, float(valor)))
        if self.fuente is not None:
            self.fuente.volume = self.volumen
        return self.volumen

    def _posiciones(self) -> list[float]:
        total = self.actual.duracion if self.actual else None
        if not total:
            return [0.0] * 5
        return [float(round(total * indice / 5 / 30) * 30) for indice in range(5)]

    def _opciones_salto(self) -> list[discord.SelectOption]:
        if self.actual is None or not self.actual.duracion:
            return [discord.SelectOption(label="Sin reproduccion", value="0")]
        total = self.actual.duracion
        paso = max(30, int(total / 8))
        opciones = []
        pos = 0
        while pos < total - 5 and len(opciones) < 10:
            opciones.append(discord.SelectOption(label=mmss(pos), value=str(pos)))
            pos += paso
        return opciones

    def _ajustar_botones(self) -> None:
        self._ajustar_vista(self.vista)

    def _ajustar_vista(self, vista: "Panel") -> None:
        pausa = discord.utils.get(vista.children, custom_id="pudin_pausa")
        if pausa is not None:
            en_pausa = bool(self.voz and self.voz.is_paused())
            pausa.emoji = "▶️" if en_pausa else "⏸️"
        salto = discord.utils.get(vista.children, custom_id="pudin_salto")
        if salto is not None:
            salto.options = self._opciones_salto()
        posiciones = self._posiciones()
        for boton in vista.posiciones:
            destino = posiciones[boton.indice]
            boton.posicion = destino
            boton.label = mmss(destino) if self.actual and self.actual.duracion else "--:--"
            boton.disabled = not (self.actual and self.actual.duracion)
        volumen = discord.utils.get(vista.children, custom_id="pudin_volumen")
        if volumen is not None:
            for opcion in volumen.options:
                opcion.default = abs(float(opcion.value) - self.volumen) < 0.01

    def texto_panel(self) -> str:
        return self._texto_panel()

    def _guild_id(self) -> int | None:
        guild = getattr(self.canal_texto, "guild", None)
        return getattr(guild, "id", None)

    def _recordar(self, clave: str, mensaje: discord.Message | None) -> None:
        guild = self._guild_id()
        if guild is None:
            return
        datos = _leer_paneles()
        actual = datos.setdefault(str(guild), {})
        if mensaje is None:
            actual.pop(clave, None)
        else:
            actual[clave] = {"canal": mensaje.channel.id, "mensaje": mensaje.id}
        _guardar_paneles(datos)

    async def _recuperar(self, clave: str) -> discord.Message | None:
        guild = self._guild_id()
        if guild is None or self.client is None:
            return None
        datos = _leer_paneles().get(str(guild), {}).get(clave)
        if not datos:
            return None
        canal = self.client.get_channel(datos["canal"])
        if canal is None:
            return None
        try:
            return await canal.fetch_message(datos["mensaje"])
        except discord.HTTPException:
            return None

    async def _editar(self, mensaje: discord.Message | None, texto: str, vista) -> discord.Message | None:
        if mensaje is None:
            return None
        try:
            return await mensaje.edit(content=texto, view=vista)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            return mensaje

    def _es_privado(self) -> bool:
        return self._guild_id() in GUILDS_PRIVADOS

    async def actualizar_panel(self) -> None:
        self._ajustar_botones()
        if self.client is not None:
            try:
                self.client.add_view(self.vista)
            except Exception:
                pass
        texto = self._texto_panel()
        privado = self._es_privado()
        self.panel = await self._editar(self.panel, texto, None if privado else self.vista)
        if privado:
            self.panel_donadores = await self._editar(self.panel_donadores, texto, self.vista)
        self._recordar("publico", self.panel)
        self._recordar("donadores", self.panel_donadores)

    async def _mostrar_panel(self) -> None:
        if self.canal_texto is None:
            return
        self._ajustar_botones()
        texto = self._texto_panel()
        privado = self._es_privado()
        vista_publica = None if privado else self.vista
        if self.panel is None:
            self.panel = await self._recuperar("publico")
        if self.panel is None:
            try:
                self.panel = await self.canal_texto.send(texto, view=vista_publica)
            except discord.HTTPException:
                pass
        else:
            self.panel = await self._editar(self.panel, texto, vista_publica)
        self._recordar("publico", self.panel)

        if not privado:
            return
        canal = canal_donadores(getattr(self.canal_texto, "guild", None))
        if canal is None:
            return
        if self.panel_donadores is None:
            self.panel_donadores = await self._recuperar("donadores")
        if self.panel_donadores is None:
            try:
                self.panel_donadores = await canal.send(texto, view=self.vista)
            except discord.HTTPException as error:
                log.warning("No pude publicar los controles de donadores: %s", error)
        else:
            self.panel_donadores = await self._editar(self.panel_donadores, texto, self.vista)
        self._recordar("donadores", self.panel_donadores)

    # reproduccion

    def _al_terminar(self, error: Exception | None) -> None:
        if error:
            log.error("Error de reproduccion: %s", error)
        self.client.loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self._avanzar())
        )

    def _borrar_actual(self) -> None:
        if self.actual and self.actual.archivo and self.actual.archivo.exists():
            try:
                self.actual.archivo.unlink()
            except OSError:
                pass

    async def _avanzar(self) -> None:
        if self._avanzando:
            return
        self._avanzando = True
        try:
            while self.cola:
                if self.voz is None or not self.voz.is_connected():
                    self.actual = None
                    await self.actualizar_panel()
                    return

                if not self.voz.is_connected():
                    try:
                        await self.voz.wait_until_connected(timeout=20)
                    except asyncio.TimeoutError:
                        log.error("La conexion de voz no termino de establecerse.")
                        return

                self._borrar_actual()
                pista = self.cola.popleft()
                self.actual = pista
                self._cargando = True
                try:
                    await self._mostrar_panel()
                except Exception as error:
                    log.warning("No pude actualizar el panel: %s", error)

                try:
                    await self.descargar(pista)
                except Exception as error:
                    self._cargando = False
                    log.error("No pude descargar %s: %s", pista.titulo, error)
                    if es_error_de_verificacion(error) and not self._avisado_cookies:
                        self._avisado_cookies = True
                        if self.canal_texto is not None:
                            try:
                                await self.canal_texto.send(
                                    "YouTube pidio verificacion de cuenta. "
                                    "Exporta tus cookies y guardalas como `cookies.txt` "
                                    "en la carpeta del bot, despues reinicia."
                                )
                            except discord.HTTPException:
                                pass
                    continue

                if not pista.url_directa and (not pista.archivo or not pista.archivo.exists()):
                    log.error("No tengo como reproducir %s, salto a la siguiente.", pista.titulo)
                    continue

                conexion = getattr(self.voz, "_connection", None)
                for _ in range(6):
                    if conexion is None or conexion.can_encrypt:
                        break
                    await asyncio.sleep(0.5)
                if conexion is not None and not conexion.can_encrypt:
                    log.warning(
                        "La sesion de voz no esta cifrada (DAVE no listo): puede que nadie escuche."
                    )

                if pista.url_directa:
                    antes = ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
                    if pista.desde:
                        antes = ["-ss", f"{pista.desde:.2f}"] + antes
                    agente = pista.cabeceras.get("User-Agent")
                    if agente:
                        antes += ["-user_agent", agente]
                    extra = {k: v for k, v in pista.cabeceras.items() if k.lower() != "user-agent"}
                    if extra:
                        antes += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in extra.items())]
                    fuente = discord.FFmpegPCMAudio(
                        pista.url_directa,
                        executable=ruta_ffmpeg() or "ffmpeg",
                        before_options=" ".join(shlex.quote(opcion) for opcion in antes),
                        options="-vn",
                    )
                else:
                    fuente = discord.FFmpegPCMAudio(
                        str(pista.archivo),
                        executable=ruta_ffmpeg() or "ffmpeg",
                        before_options=f"-ss {pista.desde:.2f}" if pista.desde else None,
                        options="-vn",
                    )

                self._cargando = False
                self.fuente = discord.PCMVolumeTransformer(fuente, volume=self.volumen)
                self.inicio = time.monotonic() - pista.desde
                self.pausado_desde = None
                self.guardar_estado()
                self.voz.play(self.fuente, after=self._al_terminar)
                log.info("Reproduciendo: %s", pista.titulo)
                try:
                    await self._mostrar_panel()
                except Exception as error:
                    log.warning("No pude actualizar el panel: %s", error)
                self.client.loop.create_task(self._precargar())
                return

            self._borrar_actual()
            self.actual = None
            self.olvidar_estado()
            await self.actualizar_panel()
        finally:
            self._avanzando = False

    async def _precargar(self) -> None:
        """Baja la proxima pista mientras suena la actual, para que no haya silencio."""
        if self._descargando or not self.cola:
            return
        siguiente = next((p for p in self.cola if p.archivo is None), None)
        if siguiente is None:
            return
        self._descargando = True
        try:
            await self.descargar(siguiente)
            log.info("Precargada: %s", siguiente.titulo)
        except Exception as error:
            log.warning("No pude precargar %s: %s", siguiente.titulo, error)
        finally:
            self._descargando = False

    async def alternar_pausa(self) -> str:
        if self.voz is None or self.actual is None:
            return "No hay nada sonando."
        if self.voz.is_paused():
            self.voz.resume()
            if self.pausado_desde is not None and self.inicio is not None:
                self.inicio += time.monotonic() - self.pausado_desde
            self.pausado_desde = None
            await self.actualizar_panel()
            return "▶️ Reanudado."
        if self.voz.is_playing():
            self.voz.pause()
            self.pausado_desde = time.monotonic()
            await self.actualizar_panel()
            return "⏸️ En pausa."
        return "No hay nada sonando."

    async def tono(self, segundos: int = 5) -> None:
        """Tono de prueba, sin pasar por YouTube."""
        if self.voz is None:
            return
        if self.voz.is_playing():
            self.voz.stop()
            await asyncio.sleep(0.5)
        fuente = discord.FFmpegPCMAudio(
            f"sine=frequency=440:duration={segundos}",
            executable=ruta_ffmpeg() or "ffmpeg",
            before_options="-f lavfi",
            options="-vn",
        )
        self.voz.play(fuente)
        log.info("Tono de prueba de %s segundos", segundos)

    async def saltar_a(self, segundos: float) -> str:
        if self.actual is None or self.voz is None:
            return "No hay nada sonando."
        pista = self.actual
        total = pista.duracion or 0
        destino = max(0.0, float(segundos))
        if total and destino >= total - 1:
            await self.saltar()
            return "Fin del tema."
        pista.desde = destino
        # se saca de "actual" para que _avanzar no borre el archivo ya descargado
        self.actual = None
        self.cola.appendleft(pista)
        self.inicio = time.monotonic() - destino
        if self.voz.is_playing() or self.voz.is_paused():
            self.voz.stop()
        else:
            await self._avanzar()
        return f"⏱️ {mmss(destino)}"

    async def mover(self, delta: float) -> str:
        return await self.saltar_a(self._transcurrido() + delta)

    async def saltar(self) -> str | None:
        anterior = self.actual.titulo if self.actual else None
        if self.voz and (self.voz.is_playing() or self.voz.is_paused()):
            self.voz.stop()
        return anterior

    async def detener(self) -> None:
        self.cola.clear()
        if self.voz and (self.voz.is_playing() or self.voz.is_paused()):
            self.voz.stop()
        self.actual = None
        self._borrar_actual()
        self.fuente = None
        self.inicio = None
        self.pausado_desde = None
        self.olvidar_estado()
        await self.actualizar_panel()

    async def desconectar(self) -> None:
        await self.detener()
        if self.voz and self.voz.is_connected():
            await self.voz.disconnect()
        self.voz = None
        self.canal_voz = None
        self.panel = None
        self.panel_donadores = None
        self.fuente = None
        self.inicio = None
        self.pausado_desde = None
        self.olvidar_estado()
