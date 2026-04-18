import re
import time
import json
import sqlite3
import os
from collections import defaultdict

import discord
from discord.ext import commands

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')

# Regex für GIF-URLs (Tenor, Giphy, direkte .gif-Links)
_GIF_PATTERN = re.compile(
    r'https?://(?:'
    r'(?:www\.)?tenor\.com/view/[^\s]+'
    r'|(?:media\d*\.)?tenor\.com/[^\s]+'
    r'|(?:www\.)?giphy\.com/[^\s]+'
    r'|media\.giphy\.com/[^\s]+'
    r'|[^\s]+\.gif(?:\?[^\s]*)?'
    r')',
    re.IGNORECASE,
)


def _load_settings() -> dict:
    defaults = {
        "gif_limit_enabled":      False,
        "gif_limit_per_minute":   3,
        "gif_limit_warn":         True,
        "gif_limit_delete":       True,
        "gif_limit_bypass_roles": [],
        "gif_limit_exempt_channels": [],
    }
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT key, value FROM bot_settings WHERE key LIKE 'gif_limit%'"
        ).fetchall()
        conn.close()
        for key, val in rows:
            try:
                defaults[key] = json.loads(val)
            except Exception:
                defaults[key] = val
    except Exception:
        pass
    return defaults


def _has_gif(message: discord.Message) -> bool:
    """True wenn die Nachricht ein GIF enthält."""
    # GIF-Datei-Anhang
    for att in message.attachments:
        if att.filename.lower().endswith('.gif'):
            return True
        if getattr(att, 'content_type', '') == 'image/gif':
            return True
    # GIF-URL im Text
    if _GIF_PATTERN.search(message.content):
        return True
    # Discord Embed mit GIF (z.B. Tenor-Preview)
    for embed in message.embeds:
        if embed.type in ('gifv', 'image'):
            url = str(embed.url or '')
            if 'tenor' in url or 'giphy' in url or url.endswith('.gif'):
                return True
    return False


class GifLimitCog(commands.Cog, name="GifLimit"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {user_id: [timestamp, timestamp, ...]} — letzte GIF-Zeitstempel
        self._gif_times: dict[int, list[float]] = defaultdict(list)

    def _is_exempt(self, member: discord.Member, s: dict) -> bool:
        """True wenn der Nutzer von der Begrenzung ausgenommen ist."""
        if member.guild_permissions.administrator:
            return True
        bypass = set(s.get("gif_limit_bypass_roles") or [])
        return bool({r.id for r in member.roles} & bypass)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return

        s = _load_settings()
        if not s.get("gif_limit_enabled"):
            return

        # Kanal ausgenommen?
        exempt_ch = set(s.get("gif_limit_exempt_channels") or [])
        if message.channel.id in exempt_ch:
            return

        if not _has_gif(message):
            return

        member = message.guild.get_member(message.author.id) if message.guild else None
        if member and self._is_exempt(member, s):
            return

        # Zeitstempel bereinigen (älter als 60s raus)
        now = time.monotonic()
        uid = message.author.id
        self._gif_times[uid] = [t for t in self._gif_times[uid] if now - t < 60.0]

        limit = int(s.get("gif_limit_per_minute") or 3)
        count = len(self._gif_times[uid])

        if count >= limit:
            # Limit überschritten
            should_delete = s.get("gif_limit_delete", True)
            should_warn   = s.get("gif_limit_warn", True)

            if should_delete:
                try:
                    await message.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass

            if should_warn:
                warn_text = (
                    f"⏱️ {message.author.mention} — Du hast das GIF-Limit erreicht "
                    f"(**{limit} GIFs/Minute**). Bitte warte kurz."
                )
                try:
                    warn_msg = await message.channel.send(warn_text, delete_after=8)
                except discord.Forbidden:
                    pass
        else:
            # GIF zählen
            self._gif_times[uid].append(now)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Auch bearbeitete Nachrichten prüfen (z.B. nachträglich eingebettete GIFs)."""
        if before.embeds == after.embeds:
            return
        await self.on_message(after)


async def setup(bot: commands.Bot):
    await bot.add_cog(GifLimitCog(bot))
