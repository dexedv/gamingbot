import discord
import sqlite3
import os
import time
from discord.ext import commands, tasks

STATS_CATEGORY_ID = 1494050170738835569
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_counter(key: str) -> int:
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT value FROM bot_settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _increment_counter(key: str, amount: int = 1):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + ? AS TEXT)",
            (key, str(amount), amount),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Cog ───────────────────────────────────────────────────────────────────────

class StatsChannelCog(commands.Cog, name="StatsChannel"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_join: dict[int, float] = {}   # user_id → monotonic join time
        self._stats_channel_id: int | None = None
        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()

    # ── Channel management ────────────────────────────────────────────────────

    async def _get_or_create_channel(self) -> discord.VoiceChannel | None:
        # Try cached ID first
        if self._stats_channel_id:
            ch = self.bot.get_channel(self._stats_channel_id)
            if isinstance(ch, discord.VoiceChannel):
                return ch

        for guild in self.bot.guilds:
            category = guild.get_channel(STATS_CATEGORY_ID)
            if not isinstance(category, discord.CategoryChannel):
                continue

            # Reuse existing stats channel if already created
            for ch in category.voice_channels:
                if ch.name.startswith("📊"):
                    self._stats_channel_id = ch.id
                    return ch

            # Create a new locked voice channel
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

    # ── Update loop ───────────────────────────────────────────────────────────

    @tasks.loop(minutes=10)
    async def update_loop(self):
        ch = await self._get_or_create_channel()
        if not ch:
            return

        msgs  = _get_counter("stats_total_messages")
        secs  = _get_counter("stats_total_voice_seconds")
        hours = round(secs / 3600, 1)

        # Format large numbers nicely
        msgs_fmt  = f"{msgs:,}".replace(",", ".")
        hours_fmt = f"{hours:,.1f}".replace(",", ".")

        new_name = f"📊 {msgs_fmt} Msg · {hours_fmt}h Voice"
        if len(new_name) > 100:
            new_name = new_name[:100]

        try:
            if ch.name != new_name:
                await ch.edit(name=new_name)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

    # ── Listeners ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        _increment_counter("stats_total_messages")

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot:
            return

        joined  = before.channel is None and after.channel is not None
        left    = before.channel is not None and after.channel is None

        if joined:
            self._voice_join[member.id] = time.monotonic()
        elif left:
            join_time = self._voice_join.pop(member.id, None)
            if join_time:
                duration = int(time.monotonic() - join_time)
                if duration > 0:
                    _increment_counter("stats_total_voice_seconds", duration)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsChannelCog(bot))
