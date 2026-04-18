from datetime import date

import discord
from discord.ext import commands
from utils import daily_coins, level_rank, xp_bar


def coin_bar(coins: int, max_coins: int = 5000) -> str:
    """Erstellt einen visuellen Münzen-Balken."""
    filled = min(int(coins / max_coins * 10), 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"`{bar}` {coins:,}"


class EconomyCog(commands.Cog, name="Economy"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── %guthaben ─────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="guthaben", aliases=["coins", "balance", "gut"])
    async def guthaben(self, ctx: commands.Context, spieler: discord.Member = None):
        target = spieler or ctx.author
        data = await self.bot.db.get_user(target.id, target.display_name)
        xp, level = await self.bot.db.get_xp(target.id)

        total = data["wins"] + data["losses"] + data["draws"]
        winrate = f"{data['wins'] / total * 100:.1f}%" if total else "–"
        emoji, rank_name = level_rank(level)

        embed = discord.Embed(
            title=f"💰  {target.display_name}",
            color=discord.Color.from_rgb(255, 200, 0),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(
            name="💳  Guthaben",
            value=coin_bar(data["coins"]),
            inline=False,
        )
        embed.add_field(
            name=f"{emoji}  Level & Rang",
            value=f"**Level {level}** — {rank_name}\n{xp_bar(xp)}",
            inline=False,
        )
        embed.add_field(name="\u200b", value="─" * 30, inline=False)
        embed.add_field(name="🏆  Siege",         value=f"**{data['wins']}**",        inline=True)
        embed.add_field(name="💔  Niederlagen",   value=f"**{data['losses']}**",      inline=True)
        embed.add_field(name="🤝  Unentschieden", value=f"**{data['draws']}**",       inline=True)
        embed.add_field(name="🎰  Slot-Spins",    value=f"**{data['total_spins']}**", inline=True)
        embed.add_field(name="📊  Siegrate",       value=f"**{winrate}**",            inline=True)
        embed.add_field(name="🎮  Spiele gesamt", value=f"**{total}**",               inline=True)

        embed.set_footer(text="Pink Horizoon Bot  •  %daily für tägliche Münzen")
        await ctx.send(embed=embed)

    # ── %daily ────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="daily")
    async def daily(self, ctx: commands.Context):
        await self.bot.db.get_user(ctx.author.id, ctx.author.display_name)

        today = str(date.today())
        last = await self.bot.db.get_last_daily(ctx.author.id)

        if last == today:
            embed = discord.Embed(
                title="⏰  Bereits abgeholt!",
                description="Du hast heute schon deine täglichen Münzen abgeholt.\nKomm **morgen** wieder!",
                color=discord.Color.from_rgb(180, 180, 180),
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

        xp, level = await self.bot.db.get_xp(ctx.author.id)
        reward = daily_coins(level)

        await self.bot.db.update_coins(ctx.author.id, reward)
        await self.bot.db.set_last_daily(ctx.author.id, today)

        # +30 XP für Daily
        old_level, new_level = await self.bot.db.add_xp(ctx.author.id, 30)
        new_coins = await self.bot.db.get_coins(ctx.author.id)

        embed = discord.Embed(
            title="🎁  Tägliche Belohnung!",
            color=discord.Color.from_rgb(87, 242, 135),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.add_field(
            name="✨  Erhaltene Münzen",
            value=f"**+{reward:,} Münzen**",
            inline=True,
        )
        embed.add_field(
            name="⭐  XP erhalten",
            value="**+30 XP**",
            inline=True,
        )
        embed.add_field(
            name="💳  Neues Guthaben",
            value=coin_bar(new_coins),
            inline=False,
        )
        embed.set_footer(text="Komm morgen wieder für mehr Münzen!")
        await ctx.send(embed=embed)

        if new_level > old_level:
            from utils import level_up_embed, send_notify
            await send_notify(self.bot, level_up_embed(ctx.author, old_level, new_level))

    # ── %bestenliste ──────────────────────────────────────────────────────────

    @commands.hybrid_command(name="bestenliste", aliases=["top", "ranking", "leaderboard"])
    async def bestenliste(self, ctx: commands.Context):
        rows = await self.bot.db.get_leaderboard(10)

        embed = discord.Embed(
            title="🏆  Münzen-Bestenliste",
            color=discord.Color.from_rgb(255, 200, 0),
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)

        if not rows:
            embed.description = "*Noch keine Spieler registriert.*"
        else:
            medals = ["🥇", "🥈", "🥉"]
            entries = []
            top = rows[0]["coins"] or 1
            for i, u in enumerate(rows):
                prefix = medals[i] if i < 3 else f"`#{i+1}`"
                bar_len = max(1, int(u["coins"] / top * 10))
                bar = "█" * bar_len + "░" * (10 - bar_len)
                entries.append(
                    f"{prefix}  **{u['username']}**\n"
                    f"╰ `{bar}`  **{u['coins']:,}** 💰"
                )
            embed.description = "\n\n".join(entries)

        embed.set_footer(text=f"Angefragt von {ctx.author.display_name}  •  %daily für tägliche Münzen")
        await ctx.send(embed=embed)

    # ── %hilfe ────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="hilfe", aliases=["help", "h"])
    async def hilfe(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎮  Pink Horizoon Bot  —  Befehlsübersicht",
            description=(
                "**Prefix: `%`**  •  Startguthaben: **500 💰**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_thumbnail(url=ctx.bot.user.display_avatar.url)

        # ── PROGRESSION ───────────────────────────────────────────────────────
        embed.add_field(
            name="📈  ╴ FORTSCHRITT ╶",
            value="\u200b",
            inline=False,
        )
        embed.add_field(
            name="💰  Wirtschaft",
            value=(
                "▸ `%guthaben` `[@spieler]`  —  Guthaben, Stats & Level\n"
                "▸ `%daily`  —  Tägliche Münzen *(steigen mit dem Level!)*\n"
                "▸ `%bestenliste`  —  Top-10 Münzen-Rangliste"
            ),
            inline=True,
        )
        embed.add_field(
            name="⭐  Level-System",
            value=(
                "▸ `%level` `[@spieler]`  —  Level, XP & Rang\n"
                "▸ `%toplevel`  —  Top-10 Level-Rangliste\n"
                "*XP durch Spielen & Daily sammeln!*"
            ),
            inline=True,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(
            name="🔥  Streak-System",
            value=(
                "▸ `%streak` `[@spieler]`  —  Tages-Streak & Meilensteine\n"
                "▸ `%topstreak`  —  Top-10 Streak-Rangliste\n"
                "*Täglich aktiv = Streak +1 → Bonus-Münzen!*"
            ),
            inline=True,
        )
        embed.add_field(
            name="📊  Aktivitäts-Ränge",
            value=(
                "▸ `%rankcard` `[@spieler]`  —  Chat- & Voice-Rang\n"
                "▸ `%chatboard`  —  Top-10 Nachrichten\n"
                "▸ `%voiceboard`  —  Top-10 Sprachzeit *(🔴 Live)*"
            ),
            inline=True,
        )

        # ── GAMES ─────────────────────────────────────────────────────────────
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(
            name="🎲  ╴ SPIELE & CASINO ╶",
            value="\u200b",
            inline=False,
        )
        embed.add_field(
            name="❌⭕  Tic-Tac-Toe",
            value=(
                "▸ `%tictactoe` `@spieler`\n"
                "🏆 **+200**  ·  💸 **−100** Münzen"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎰  Spielautomat",
            value=(
                "▸ `%slots` `<einsatz>` *(10–1000)*\n"
                "Jackpot **50×**  ·  Bonus **×1–9**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🃏  Blackjack",
            value=(
                "▸ `%bj` `<einsatz>` *(10–2000)*\n"
                "Hit · Stand · Double · **1.5×**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎡  Roulette",
            value=(
                "▸ `%roulette` `<einsatz>` `<wette>` *(10–5000)*\n"
                "`rot/schwarz` **2×**  ·  Zahl **36×**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎲  Minispiele",
            value=(
                "▸ `%cf` `<einsatz>`  —  Coinflip *(2×)*\n"
                "▸ `%würfeln` `<einsatz>`  —  Würfeln *(2×)*\n"
                "▸ `%hl` `<einsatz>`  —  Higher or Lower"
            ),
            inline=True,
        )

        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.set_footer(
            text=f"Angefragt von {ctx.author.display_name}  •  Viel Glück! 🍀",
            icon_url=ctx.author.display_avatar.url,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(EconomyCog(bot))
