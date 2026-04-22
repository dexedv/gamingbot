import discord
import sqlite3
import os
from discord.ext import commands, tasks

STATS_CATEGORY_ID = 1494050170738835569
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')


def _get_stats() -> tuple[int, int]:
    """Returns (total_messages, total_voice_seconds) from users table."""
    try:
        conn = sqlite3.connect(DB_PATH)
        msgs = conn.execute("SELECT SUM(message_count) FROM users").fetchone()[0] or 0
        secs = conn.execute("SELECT SUM(voice_seconds) FROM users").fetchone()[0] or 0
        conn.close()
        return int(msgs), int(secs)
    except Exception:
        return 0, 0


MC_SERVER = "play.pinkhorizon.fun"
MC_CHANNEL_NAME = f"🎮 MC: {MC_SERVER}"


class StatsChannelCog(commands.Cog, name="StatsChannel"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._stats_channel_id: int | None = None
        self._mc_channel_id: int | None = None
        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()

    async def _get_or_create_channel(self) -> discord.VoiceChannel | None:
        if self._stats_channel_id:
            ch = self.bot.get_channel(self._stats_channel_id)
            if isinstance(ch, discord.VoiceChannel):
                return ch

        for guild in self.bot.guilds:
            category = guild.get_channel(STATS_CATEGORY_ID)
            if not isinstance(category, discord.CategoryChannel):
                continue

            for ch in category.voice_channels:
                if ch.name.startswith("📊"):
                    self._stats_channel_id = ch.id
                    return ch

            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        view_channel=True,
                        connect=False,
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        connect=True,
                        manage_channels=True,
                    ),
                }
                ch = await guild.create_voice_channel(
                    name="📊 Lade…",
                    category=category,
                    overwrites=overwrites,
                )
                self._stats_channel_id = ch.id
                return ch
            except discord.Forbidden:
                pass

        return None

    async def _get_or_create_mc_channel(self) -> discord.VoiceChannel | None:
        if self._mc_channel_id:
            ch = self.bot.get_channel(self._mc_channel_id)
            if isinstance(ch, discord.VoiceChannel):
                return ch

        for guild in self.bot.guilds:
            category = guild.get_channel(STATS_CATEGORY_ID)
            if not isinstance(category, discord.CategoryChannel):
                print(f"[MC-Channel] Kategorie {STATS_CATEGORY_ID} nicht gefunden in {guild.name}")
                continue

            for ch in category.voice_channels:
                if ch.name.startswith("🎮"):
                    self._mc_channel_id = ch.id
                    return ch

            print(f"[MC-Channel] Erstelle Channel in {guild.name} / {category.name} ...")
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        view_channel=True,
                        connect=False,
                    ),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        connect=True,
                        manage_channels=True,
                    ),
                }
                ch = await guild.create_voice_channel(
                    name=MC_CHANNEL_NAME,
                    category=category,
                    overwrites=overwrites,
                )
                self._mc_channel_id = ch.id
                print(f"[MC-Channel] Erstellt: {ch.name} (ID: {ch.id})")
                return ch
            except Exception as e:
                print(f"[MC-Channel] FEHLER beim Erstellen: {type(e).__name__}: {e}")

        return None

    @tasks.loop(minutes=10)
    async def update_loop(self):
        ch = await self._get_or_create_channel()
        if ch:
            msgs, secs = _get_stats()
            hours = round(secs / 3600, 1)

            msgs_fmt  = f"{msgs:,}".replace(",", ".")
            hours_fmt = str(hours).replace(".", ",")

            new_name = f"📊 {msgs_fmt} Msg · {hours_fmt}h Voice"
            if len(new_name) > 100:
                new_name = new_name[:100]

            try:
                if ch.name != new_name:
                    await ch.edit(name=new_name)
            except (discord.Forbidden, discord.HTTPException):
                pass

        mc_ch = await self._get_or_create_mc_channel()
        if mc_ch:
            try:
                if mc_ch.name != MC_CHANNEL_NAME:
                    await mc_ch.edit(name=MC_CHANNEL_NAME)
            except (discord.Forbidden, discord.HTTPException):
                pass

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        await self._get_or_create_mc_channel()

    @discord.app_commands.command(name="mc_kanal", description="Erstellt den MC-Kanal (Admin)")
    @discord.app_commands.default_permissions(administrator=True)
    async def mc_kanal(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        for guild in self.bot.guilds:
            category = guild.get_channel(STATS_CATEGORY_ID)
            if not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send(f"❌ Kategorie `{STATS_CATEGORY_ID}` nicht gefunden.", ephemeral=True)
                return
            await interaction.followup.send(f"✅ Kategorie gefunden: **{category.name}**\nErstelle Channel...", ephemeral=True)
        ch = await self._get_or_create_mc_channel()
        if ch:
            await interaction.followup.send(f"✅ Channel erstellt/gefunden: {ch.mention}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Channel konnte nicht erstellt werden (Keine Berechtigung?)", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsChannelCog(bot))
