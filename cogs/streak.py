import json
import os
import discord
from discord.ext import commands, tasks
from utils import base_name, is_name_protected

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '..', 'settings.json')


def _nickname_updates_enabled() -> bool:
    import sqlite3
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT value FROM bot_settings WHERE key = 'nickname_updates'").fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    # Fallback: settings.json
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f).get("nickname_updates", True)
    except Exception:
        return True

# Meilensteine: Tage → (Emoji, Name, Bonus-Münzen)
MILESTONES = {
    7:   ("🔥", "1 Woche",    100),
    14:  ("🔥", "2 Wochen",   200),
    30:  ("💫", "1 Monat",    500),
    60:  ("💫", "2 Monate",   750),
    100: ("⭐", "100 Tage",  1000),
    150: ("⭐", "150 Tage",  1500),
    200: ("🌟", "200 Tage",  2000),
    300: ("🌟", "300 Tage",  3000),
    365: ("👑", "1 Jahr",    5000),
    500: ("👑", "500 Tage",  7500),
    750: ("💎", "750 Tage", 10000),
    900: ("💎", "900 Tage", 15000),
}


def streak_bar(streak: int, width: int = 10) -> str:
    filled = min(int(streak / 900 * width), width)
    bar = "🟥" * filled + "⬛" * (width - filled)
    return f"{bar}  **{streak}** / 900 Tage"


def streak_rank(streak: int) -> tuple[str, str]:
    if streak < 7:
        return "🌱", "Neuling"
    if streak < 30:
        return "🔥", "Aktiv"
    if streak < 100:
        return "💫", "Veteran"
    if streak < 200:
        return "⭐", "Legende"
    if streak < 365:
        return "🌟", "Elite"
    if streak < 750:
        return "👑", "Meister"
    return "💎", "Unsterblich"


STREAK_EMOJI = "🔥"


async def update_nickname(member: discord.Member, streak: int, force: bool = False) -> bool:
    """Gibt True zurück wenn der Nickname tatsächlich geändert wurde."""
    if not force and not _nickname_updates_enabled():
        return False
    if is_name_protected(member):
        return False
    try:
        new_nick = f"{base_name(member.display_name)} | {streak}{STREAK_EMOJI}"
        if len(new_nick) > 32:
            new_nick = new_nick[:32]
        if member.display_name != new_nick:
            await member.edit(nick=new_nick)
            return True
    except discord.Forbidden:
        pass
    return False


class StreakCog(commands.Cog, name="Streak"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldown: set[int] = set()
        self.nickname_loop.start()

    def cog_unload(self):
        self.nickname_loop.cancel()

    async def run_nickname_update(self, force: bool = False, scheduled: bool = False):
        """Aktualisiert alle Nicknames sofort (auch manuell aufrufbar)."""
        from utils import send_log
        import aiosqlite
        if scheduled:
            await send_log(self.bot, "🔄 Nickname-Update gestartet",
                           "⏰  Automatischer **5h-Lauf** wurde gestartet…",
                           discord.Color.from_rgb(251, 146, 60))

        async with aiosqlite.connect(self.bot.db.db_path) as db:
            cur = await db.execute("SELECT user_id, streak FROM users")
            streaks = {row[0]: row[1] for row in await cur.fetchall()}

        updated = 0
        skipped = 0
        for guild in self.bot.guilds:
            async for member in guild.fetch_members(limit=None):
                if member.bot:
                    continue
                streak = streaks.get(member.id, 0)
                result = await update_nickname(member, streak, force=force)
                if result:
                    updated += 1
                else:
                    skipped += 1

        if scheduled or force:
            label = "5h-Lauf" if scheduled else "Manueller Lauf"
            await send_log(
                self.bot,
                "✅ Nickname-Update abgeschlossen",
                f"🏷️  **Aktualisiert:** {updated} Nicknames\n"
                f"⏩  **Übersprungen:** {skipped} Mitglieder\n"
                f"📋  **Modus:** {label}",
                discord.Color.from_rgb(34, 197, 94),
            )

    @tasks.loop(hours=5)
    async def nickname_loop(self):
        """Alle 5 Stunden alle Nicknames aktualisieren."""
        await self.run_nickname_update(scheduled=True)

    @nickname_loop.before_loop
    async def before_nickname_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        """Beim Start sofort alle Nicknames setzen."""
        await self.run_nickname_update()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.author.id in self._cooldown:
            return

        db = self.bot.db
        user = message.author

        # Sicherstellen dass User in DB ist
        await db.get_user(user.id, user.display_name)

        old_streak, new_streak = await db.update_streak(user.id)

        if new_streak == old_streak:
            self._cooldown.add(user.id)
            return

        self._cooldown.add(user.id)

        # Nickname aktualisieren
        await update_nickname(user, new_streak)

        # Meilenstein erreicht?
        if new_streak in MILESTONES:
            emoji, name, bonus = MILESTONES[new_streak]
            await db.update_coins(user.id, bonus)
            new_coins = await db.get_coins(user.id)

            embed = discord.Embed(
                title=f"{emoji}  Streak-Meilenstein erreicht!",
                description=(
                    f"**{user.display_name}** hat **{new_streak} Tage** in Folge aktiv!\n"
                    f"Meilenstein: **{name}** {emoji}"
                ),
                color=discord.Color.from_rgb(255, 215, 0),
            )
            embed.add_field(name="🎁  Bonus", value=f"**+{bonus:,} Münzen**", inline=True)
            embed.add_field(name="💳  Guthaben", value=f"{new_coins:,} Münzen", inline=True)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"🔥 {new_streak} Tage Streak  •  Weiter so!")
            from utils import send_notify
            await send_notify(self.bot, embed)

    @commands.command(name="updatenicks", hidden=True)
    async def update_nicks_cmd(self, ctx: commands.Context):
        """Aktualisiert alle Nicknames manuell (nur Owner)."""
        if ctx.author.id != 307210134856400908:
            return
        msg = await ctx.send("⏳ Aktualisiere alle Nicknames…")
        await self.run_nickname_update(force=True)
        await msg.edit(content="✅ Alle Nicknames wurden aktualisiert.")

    @commands.hybrid_command(name="streak", aliases=["tage", "aktivität"])
    async def streak_cmd(self, ctx: commands.Context, member: discord.Member = None):
        """Zeigt deinen Tages-Streak an — %streak [@nutzer]"""
        target = member or ctx.author
        await self.bot.db.get_user(target.id, target.display_name)
        streak, max_streak = await self.bot.db.get_streak(target.id)

        emoji, rank = streak_rank(streak)
        bar = streak_bar(streak)

        # Nächsten Meilenstein finden
        next_milestone = next((d for d in sorted(MILESTONES) if d > streak), 900)
        days_left = next_milestone - streak
        ms_emoji, ms_name, ms_bonus = MILESTONES.get(next_milestone, ("💎", "900 Tage", 15000))

        embed = discord.Embed(
            title=f"{emoji}  Tages-Streak  —  {rank}",
            color=discord.Color.from_rgb(255, 100, 0),
        )
        embed.add_field(name="🔥  Aktueller Streak", value=bar,                          inline=False)
        embed.add_field(name="🏆  Rekord",            value=f"**{max_streak}** Tage",    inline=True)
        embed.add_field(name="📅  Rang",              value=f"{emoji} {rank}",           inline=True)
        embed.add_field(
            name=f"🎯  Nächster Meilenstein",
            value=f"{ms_emoji} **{ms_name}** in **{days_left}** Tagen\nBonus: **+{ms_bonus:,} Münzen**",
            inline=False,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"🎮 {target.display_name}  •  Jeden Tag aktiv = Streak +1")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="topstreak", aliases=["streakboard"])
    async def top_streak(self, ctx: commands.Context):
        """Top-10 Streak-Bestenliste — %topstreak"""
        async with __import__("aiosqlite").connect(self.bot.db.db_path) as db:
            db.row_factory = __import__("aiosqlite").Row
            cur = await db.execute(
                "SELECT username, streak, max_streak FROM users ORDER BY streak DESC LIMIT 10"
            )
            rows = await cur.fetchall()

        if not rows:
            await ctx.send("Noch keine Einträge!")
            return

        medals = ["🥇", "🥈", "🥉"]
        entries = []
        top_streak = rows[0]["streak"] or 1
        for i, row in enumerate(rows):
            prefix = medals[i] if i < 3 else f"`#{i+1}`"
            emoji, rank = streak_rank(row["streak"])
            bar_len = max(1, int(row["streak"] / top_streak * 10))
            bar = "█" * bar_len + "░" * (10 - bar_len)
            entries.append(
                f"{prefix}  **{row['username']}**\n"
                f"╰ `{bar}`  {emoji} **{row['streak']} Tage** — Rekord: {row['max_streak']}"
            )

        embed = discord.Embed(
            title="🔥  Streak-Bestenliste  —  Top 10",
            description="\n\n".join(entries),
            color=discord.Color.from_rgb(255, 100, 0),
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild and ctx.guild.icon else None)
        embed.set_footer(text=f"Angefragt von {ctx.author.display_name}  •  Jeden Tag aktiv = Streak +1!")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(StreakCog(bot))
