import discord
import time
from discord.ext import commands, tasks

# ── Chat-Ränge ────────────────────────────────────────────────────────────────
CHAT_RANKS = [
    (0,     "⬛", "Stiller Beobachter"),
    (50,    "📝", "Schreiber"),
    (200,   "💬", "Gesprächig"),
    (500,   "🗣️", "Redner"),
    (1000,  "📢", "Diskutant"),
    (2500,  "⭐", "Aktiver"),
    (5000,  "🌟", "Veteran"),
    (10000, "💎", "Elite"),
    (25000, "👑", "Legende"),
]

# ── Voice-Ränge (in Sekunden) ─────────────────────────────────────────────────
VOICE_RANKS = [
    (0,          "🔇", "Stiller Zuhörer"),
    (3600,       "🔉", "Teilnehmer"),        # 1h
    (18000,      "🔊", "Gesprächspartner"),  # 5h
    (36000,      "🎙️", "Redner"),            # 10h
    (90000,      "⭐", "Aktiver"),           # 25h
    (180000,     "🌟", "Veteran"),           # 50h
    (360000,     "💎", "Elite"),             # 100h
    (720000,     "👑", "Legende"),           # 200h
]


def get_chat_rank(messages: int) -> tuple[str, str, int, int | None]:
    rank = CHAT_RANKS[0]
    for r in CHAT_RANKS:
        if messages >= r[0]:
            rank = r
        else:
            break
    idx = CHAT_RANKS.index(rank)
    next_t = CHAT_RANKS[idx + 1][0] if idx + 1 < len(CHAT_RANKS) else None
    return rank[1], rank[2], rank[0], next_t


def get_voice_rank(seconds: int) -> tuple[str, str, int, int | None]:
    rank = VOICE_RANKS[0]
    for r in VOICE_RANKS:
        if seconds >= r[0]:
            rank = r
        else:
            break
    idx = VOICE_RANKS.index(rank)
    next_t = VOICE_RANKS[idx + 1][0] if idx + 1 < len(VOICE_RANKS) else None
    return rank[1], rank[2], rank[0], next_t


def fmt_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def fmt_seconds_next(seconds: int) -> str:
    """Für den Threshold-Wert (ohne Sekunden)."""
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h:
        return f"{h}h" + (f" {m}m" if m else "")
    return f"{m}m"


def progress_bar(current: int, current_thresh: int, next_thresh, width: int = 10) -> str:
    if next_thresh is None:
        return "█" * width + "  **MAX**"
    progress = max(0, (current - current_thresh) / (next_thresh - current_thresh))
    filled = min(int(progress * width), width)
    bar = "█" * filled + "░" * (width - filled)
    return f"`{bar}`"


class RanksCog(commands.Cog, name="Ranks"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._voice_sessions: dict[int, float] = {}
        self._msg_xp_count: dict[int, int] = {}  # user_id → verbleibende XP-Grants diese Minute
        self.save_voice_loop.start()

    def cog_unload(self):
        self.save_voice_loop.cancel()

    @staticmethod
    def _is_muted(state: discord.VoiceState) -> bool:
        """True wenn der Nutzer stummgeschaltet ist (selbst oder durch Server)."""
        return state.self_mute or state.mute

    # ── Beim Start: bestehende Voice-Sessions erfassen ────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot and member.id not in self._voice_sessions:
                        if member.voice and not self._is_muted(member.voice):
                            self._voice_sessions[member.id] = time.time()

    # ── Alle 30 Sek Voice-Zeit speichern ─────────────────────────────────────

    @tasks.loop(seconds=30)
    async def save_voice_loop(self):
        now = time.time()
        for user_id, start in list(self._voice_sessions.items()):
            secs = int(now - start)
            if secs > 0:
                await self.bot.db.add_voice_seconds(user_id, secs)
                await self.bot.db.add_xp(user_id, 1)  # 1 XP pro 30s Voice
                self._voice_sessions[user_id] = now  # Timer zurücksetzen

    @save_voice_loop.before_loop
    async def before_save_voice_loop(self):
        await self.bot.wait_until_ready()

    # ── Message tracking ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await self.bot.db.get_user(message.author.id, message.author.display_name)
        await self.bot.db.add_message(message.author.id)

        # 2 XP pro Nachricht, max. 5× pro Minute
        uid = message.author.id
        remaining = self._msg_xp_count.get(uid, 5)
        if remaining > 0:
            self._msg_xp_count[uid] = remaining - 1
            old_level, new_level = await self.bot.db.add_xp(uid, 2)
            if new_level > old_level:
                from utils import level_up_embed
                await message.channel.send(embed=level_up_embed(message.author, old_level, new_level))
            if remaining == 5:  # Erstes Grant dieser Minute → Reset planen
                async def _reset(u=uid):
                    import asyncio
                    await asyncio.sleep(60)
                    self._msg_xp_count.pop(u, None)
                self.bot.loop.create_task(_reset())

    # ── Voice tracking ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        if member.bot:
            return

        if before.channel is None and after.channel is not None:
            # Joined voice — nur tracken wenn nicht gemutet
            if not self._is_muted(after):
                self._voice_sessions[member.id] = time.time()

            # Streak beim Voice-Beitritt aktualisieren (unabhängig vom Mute)
            await self.bot.db.get_user(member.id, member.display_name)
            old_streak, new_streak = await self.bot.db.update_streak(member.id)
            if new_streak != old_streak:
                from cogs.streak import update_nickname, MILESTONES
                await update_nickname(member, new_streak)
                if new_streak in MILESTONES:
                    emoji, name, bonus = MILESTONES[new_streak]
                    await self.bot.db.update_coins(member.id, bonus)

        elif before.channel is not None and after.channel is None:
            # Left voice — Zeit speichern
            start = self._voice_sessions.pop(member.id, None)
            if start:
                secs = int(time.time() - start)
                if secs > 0:
                    await self.bot.db.get_user(member.id, member.display_name)
                    await self.bot.db.add_voice_seconds(member.id, secs)

        elif before.channel is not None and after.channel is not None:
            was_muted = self._is_muted(before)
            now_muted = self._is_muted(after)

            if was_muted and not now_muted:
                # Entmutet → Tracking starten
                self._voice_sessions[member.id] = time.time()

            elif not was_muted and now_muted:
                # Gemutet → Zeit speichern und Tracking stoppen
                start = self._voice_sessions.pop(member.id, None)
                if start:
                    secs = int(time.time() - start)
                    if secs > 0:
                        await self.bot.db.add_voice_seconds(member.id, secs)

            elif before.channel != after.channel:
                # Channel-Wechsel (kein Mute-Change) → Session sicherstellen
                if not now_muted and member.id not in self._voice_sessions:
                    self._voice_sessions[member.id] = time.time()

    # ── %rankcard ─────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="rankcard", aliases=["rank", "stats", "aktivrang"])
    async def rankcard(self, ctx: commands.Context, member: discord.Member = None):
        """Zeigt Chat- & Voice-Rang — %rankcard [@nutzer]"""
        target = member or ctx.author
        await self.bot.db.get_user(target.id, target.display_name)
        msgs, voice_secs_db = await self.bot.db.get_chat_voice_stats(target.id)

        # Live Voice-Session dazurechnen
        live_start = self._voice_sessions.get(target.id)
        live_secs = int(time.time() - live_start) if live_start else 0
        total_secs = voice_secs_db + live_secs

        c_emoji, c_name, c_thresh, c_next = get_chat_rank(msgs)
        v_emoji, v_name, v_thresh, v_next = get_voice_rank(total_secs)

        # Nächste Rang-Namen
        c_next_name = next((r[2] for r in CHAT_RANKS  if r[0] == c_next), None) if c_next else None
        v_next_name = next((r[2] for r in VOICE_RANKS if r[0] == v_next), None) if v_next else None

        # Fortschritt in %
        c_pct = int((msgs - c_thresh) / (c_next - c_thresh) * 100) if c_next else 100
        v_pct = int((total_secs - v_thresh) / (v_next - v_thresh) * 100) if v_next else 100

        # Progress-Balken (12 Zeichen)
        def pbar(pct: int, width: int = 12) -> str:
            filled = min(int(pct / 100 * width), width)
            return "█" * filled + "░" * (width - filled)

        # Dynamische Farbe nach bestem Rang
        top_emoji = c_emoji if CHAT_RANKS.index(next(r for r in CHAT_RANKS if r[1] == c_emoji)) \
                             >= VOICE_RANKS.index(next(r for r in VOICE_RANKS if r[1] == v_emoji)) \
                             else v_emoji
        color_map = {
            "👑": discord.Color.from_rgb(255, 215, 0),
            "💎": discord.Color.from_rgb(0, 220, 255),
            "🌟": discord.Color.from_rgb(255, 165, 0),
            "⭐": discord.Color.from_rgb(255, 200, 50),
            "📢": discord.Color.from_rgb(160, 100, 255),
            "🗣️": discord.Color.from_rgb(100, 200, 255),
            "💬": discord.Color.from_rgb(87, 200, 140),
            "🔊": discord.Color.from_rgb(87, 200, 140),
        }
        color = color_map.get(top_emoji, discord.Color.from_rgb(88, 101, 242))

        embed = discord.Embed(
            title=f"📊  {target.display_name}",
            description=(
                f"{c_emoji} **{c_name}**  ╱  {v_emoji} **{v_name}**"
                + (f"\n🔴 **Live im Voice** — +{fmt_seconds(live_secs)}" if live_secs > 0 else "")
            ),
            color=color,
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        # ── Chat ──────────────────────────────────────────────────────────────
        embed.add_field(name="\u200b", value="**💬  Chat-Rang**", inline=False)
        embed.add_field(
            name=f"{c_emoji}  {c_name}",
            value=(
                f"`{pbar(c_pct)}`  **{c_pct}%**\n"
                f"**{msgs:,}** Nachrichten"
            ),
            inline=True,
        )
        if c_next_name:
            embed.add_field(
                name="🎯  Nächster Rang",
                value=(
                    f"**{c_next_name}**\n"
                    f"Noch **{c_next - msgs:,}** Nachrichten"
                ),
                inline=True,
            )
        else:
            embed.add_field(name="🏆  Status", value="**Maximum erreicht!**", inline=True)

        # ── Voice ─────────────────────────────────────────────────────────────
        embed.add_field(name="\u200b", value="**🎙️  Voice-Rang**", inline=False)
        embed.add_field(
            name=f"{v_emoji}  {v_name}",
            value=(
                f"`{pbar(v_pct)}`  **{v_pct}%**\n"
                f"**{fmt_seconds(total_secs)}** Sprachzeit"
            ),
            inline=True,
        )
        if v_next_name:
            remaining = fmt_seconds(v_next - total_secs)
            embed.add_field(
                name="🎯  Nächster Rang",
                value=(
                    f"**{v_next_name}**\n"
                    f"Noch **{remaining}**"
                ),
                inline=True,
            )
        else:
            embed.add_field(name="🏆  Status", value="**Maximum erreicht!**", inline=True)

        embed.set_footer(
            text=f"💬 Schreiben & 🎙️ Sprechen steigern den Rang!",
            icon_url=target.display_avatar.url,
        )
        await ctx.send(embed=embed)

    # ── %chatboard ────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="chatboard", aliases=["topchat", "nachrichten"])
    async def chatboard(self, ctx: commands.Context):
        """Top-10 nach Nachrichten — %chatboard"""
        rows = await self.bot.db.get_chat_leaderboard(10)
        medals = ["🥇", "🥈", "🥉"]
        entries = []
        top_msgs = (rows[0]["message_count"] if rows else 1) or 1
        for i, u in enumerate(rows):
            prefix = medals[i] if i < 3 else f"`#{i+1}`"
            emoji, name, _, _ = get_chat_rank(u["message_count"])
            bar_len = max(1, int(u["message_count"] / top_msgs * 10))
            bar = "█" * bar_len + "░" * (10 - bar_len)
            entries.append(
                f"{prefix}  **{u['username']}**\n"
                f"╰ `{bar}`  {emoji} **{name}** — {u['message_count']:,} Nachrichten"
            )
        embed = discord.Embed(
            title="💬  Chat-Bestenliste  —  Top 10",
            description="\n\n".join(entries) if entries else "*Noch keine Einträge.*",
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild and ctx.guild.icon else None)
        embed.set_footer(text=f"Angefragt von {ctx.author.display_name}  •  Mehr schreiben = höherer Rang!")
        await ctx.send(embed=embed)

    # ── %voiceboard ───────────────────────────────────────────────────────────

    @commands.hybrid_command(name="voiceboard", aliases=["topvoice", "sprachzeit"])
    async def voiceboard(self, ctx: commands.Context):
        """Top-10 nach Sprachzeit — %voiceboard"""
        rows = await self.bot.db.get_voice_leaderboard(10)
        medals = ["🥇", "🥈", "🥉"]
        entries = []
        all_secs = []
        for u in rows:
            secs = u["voice_seconds"]
            live_start = self._voice_sessions.get(u["user_id"])
            if live_start:
                secs += int(time.time() - live_start)
            all_secs.append(secs)
        top_secs = (all_secs[0] if all_secs else 1) or 1
        for i, (u, secs) in enumerate(zip(rows, all_secs)):
            prefix = medals[i] if i < 3 else f"`#{i+1}`"
            emoji, name, _, _ = get_voice_rank(secs)
            bar_len = max(1, int(secs / top_secs * 10))
            bar = "█" * bar_len + "░" * (10 - bar_len)
            live_hint = "  🔴 *Live*" if self._voice_sessions.get(u["user_id"]) else ""
            entries.append(
                f"{prefix}  **{u['username']}**{live_hint}\n"
                f"╰ `{bar}`  {emoji} **{name}** — {fmt_seconds(secs)}"
            )
        embed = discord.Embed(
            title="🎙️  Voice-Bestenliste  —  Top 10",
            description="\n\n".join(entries) if entries else "*Noch keine Einträge.*",
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild and ctx.guild.icon else None)
        embed.set_footer(text=f"Angefragt von {ctx.author.display_name}  •  🔴 = gerade im Voice")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RanksCog(bot))
