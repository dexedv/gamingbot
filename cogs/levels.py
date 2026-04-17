import discord
from discord.ext import commands
from utils import level_from_xp, xp_bar, xp_to_next_level, level_rank, daily_coins


class LevelsCog(commands.Cog, name="Levels"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="level", aliases=["lvl", "xp", "rang"])
    async def level_cmd(self, ctx: commands.Context, member: discord.Member = None):
        """Zeigt dein Level, XP und Rang an — %level [@nutzer]"""
        target = member or ctx.author
        await self.bot.db.get_user(target.id, target.display_name)
        xp, level = await self.bot.db.get_xp(target.id)

        emoji, rank_name = level_rank(level)
        bar  = xp_bar(xp)
        need = xp_to_next_level(xp)
        dc   = daily_coins(level)

        embed = discord.Embed(
            title=f"{emoji}  Level {level}  —  {rank_name}",
            color=discord.Color.from_rgb(255, 215, 0),
        )
        embed.add_field(name="📊  XP-Fortschritt", value=bar,                   inline=False)
        embed.add_field(name="⬆️  Bis Level-Up",   value=f"{need:,} XP",        inline=True)
        embed.add_field(name="💰  Tägliche Münzen", value=f"{dc:,} Münzen",      inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"🎮 {target.display_name}  •  Gesamt-XP: {xp:,}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="toplevel", aliases=["lvlboard", "ranglist"])
    async def top_level(self, ctx: commands.Context):
        """Zeigt die Top-10 nach Level — %toplevel"""
        async with __import__("aiosqlite").connect(self.bot.db.db_path) as db:
            db.row_factory = __import__("aiosqlite").Row
            cur = await db.execute(
                "SELECT username, xp, level FROM users ORDER BY xp DESC LIMIT 10"
            )
            rows = await db.fetchall() if False else await cur.fetchall()

        if not rows:
            await ctx.send("Noch keine Einträge!")
            return

        medals = ["🥇", "🥈", "🥉"]
        entries = []
        top_xp = rows[0]["xp"] or 1
        for i, row in enumerate(rows):
            prefix = medals[i] if i < 3 else f"`#{i+1}`"
            emoji, rank_name = level_rank(row["level"])
            bar_len = max(1, int(row["xp"] / top_xp * 10))
            bar = "█" * bar_len + "░" * (10 - bar_len)
            entries.append(
                f"{prefix}  **{row['username']}**\n"
                f"╰ `{bar}`  {emoji} **Lv.{row['level']}** — {row['xp']:,} XP"
            )

        embed = discord.Embed(
            title="⭐  Level-Bestenliste  —  Top 10",
            description="\n\n".join(entries),
            color=discord.Color.from_rgb(255, 215, 0),
        )
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild and ctx.guild.icon else None)
        embed.set_footer(text=f"Angefragt von {ctx.author.display_name}  •  XP durch Spielen sammeln!")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelsCog(bot))
