import discord
import sqlite3
import os
from discord.ext import commands
from utils import send_log

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')
AUTO_JAIL_AT = 5


# ── DB-Helfer ─────────────────────────────────────────────────────────────────

def _total_warns(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM warns WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def _add_warn(user_id: int, username: str, mod_id: int, mod_name: str, amount: int, reason: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO warns (user_id, username, moderator_id, moderator_name, amount, reason)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, mod_id, mod_name, amount, reason),
    )
    conn.commit()
    conn.close()


def _clear_warns(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM warns WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def _get_warn_history(user_id: int) -> list:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT amount, reason, moderator_name, warned_at FROM warns"
        " WHERE user_id = ? ORDER BY warned_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


# ── Cog ───────────────────────────────────────────────────────────────────────

class WarnsCog(commands.Cog, name="Warns"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="warn")
    @commands.has_permissions(kick_members=True)
    async def warn_cmd(self, ctx: commands.Context, member: discord.Member, amount_or_reason: str = "1", *, rest: str = ""):
        """Verwarnt einen Nutzer — %warn @nutzer [anzahl] [grund]"""
        # Anzahl oder direkt Grund?
        try:
            amount = int(amount_or_reason)
            reason = rest or "Kein Grund angegeben"
        except ValueError:
            amount = 1
            reason = (amount_or_reason + (" " + rest if rest else "")).strip() or "Kein Grund angegeben"

        amount = max(1, min(amount, 10))

        if member.bot:
            await ctx.send("❌ Bots können nicht verwarnt werden.", delete_after=5)
            return
        if member == ctx.author:
            await ctx.send("❌ Du kannst dich nicht selbst verwarnen.", delete_after=5)
            return
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("❌ Du kannst diesen Nutzer nicht verwarnen (gleiche oder höhere Rolle).", delete_after=5)
            return

        _add_warn(member.id, str(member), ctx.author.id, str(ctx.author), amount, reason)
        total = _total_warns(member.id)

        # DM senden
        try:
            dm = discord.Embed(
                title="⚠️ Du wurdest verwarnt",
                description=f"Du hast auf **{ctx.guild.name}** eine Verwarnung erhalten.",
                color=discord.Color.orange(),
            )
            dm.add_field(name="📝 Grund",                value=reason,           inline=False)
            dm.add_field(name="⚠️ Verwarnungen gesamt",  value=f"**{total}** / {AUTO_JAIL_AT}", inline=True)
            dm.add_field(name="👮 Von",                  value=str(ctx.author),  inline=True)
            if total >= AUTO_JAIL_AT:
                dm.add_field(name="🔒 Hinweis", value="Du wirst automatisch in den Knast gesperrt!", inline=False)
            await member.send(embed=dm)
        except Exception:
            pass

        color = discord.Color.red() if total >= AUTO_JAIL_AT else discord.Color.orange()
        embed = discord.Embed(
            title="⚠️ Verwarnung ausgesprochen",
            description=f"{member.mention} wurde verwarnt.",
            color=color,
        )
        embed.add_field(name="📝 Grund",   value=reason,                       inline=False)
        embed.add_field(name="🔢 Anzahl",  value=f"+{amount}",                 inline=True)
        embed.add_field(name="⚠️ Gesamt",  value=f"**{total}** / {AUTO_JAIL_AT}", inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Von {ctx.author.display_name}")

        await ctx.send(embed=embed)
        await send_log(
            self.bot,
            "⚠️ Verwarnung",
            f"👤  **Nutzer:** {member.mention} (`{member.id}`)\n"
            f"👮  **Von:** {ctx.author}\n"
            f"🔢  **Anzahl:** +{amount} (gesamt: {total})\n"
            f"📝  **Grund:** {reason}",
            discord.Color.orange(),
        )

        # Auto-Knast bei 5+
        if total >= AUTO_JAIL_AT:
            knast = self.bot.cogs.get("Knast")
            if knast:
                result = await knast.jail_member(
                    member,
                    reason=f"Automatisch: {total} Verwarnungen erreicht",
                    by_name="Auto-Warnsystem",
                    by_id=0,
                )
                if result.get("ok"):
                    await ctx.send(
                        f"🔒 **{member.display_name}** wurde automatisch in den Knast gesperrt "
                        f"({total} Verwarnungen)."
                    )

    @commands.command(name="warns")
    async def warns_cmd(self, ctx: commands.Context, member: discord.Member = None):
        """Zeigt Verwarnungen eines Nutzers — %warns [@nutzer]"""
        target = member or ctx.author
        total   = _total_warns(target.id)
        history = _get_warn_history(target.id)

        embed = discord.Embed(
            title=f"⚠️ Verwarnungen — {target.display_name}",
            color=discord.Color.orange() if total > 0 else discord.Color.green(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        bar_filled = min(total, AUTO_JAIL_AT)
        bar = "🟧" * bar_filled + "⬛" * (AUTO_JAIL_AT - bar_filled)
        embed.add_field(
            name="⚠️ Gesamt",
            value=f"{bar}  **{total}** / {AUTO_JAIL_AT}",
            inline=False,
        )

        if history:
            lines = []
            for amount, reason, mod_name, warned_at in history[:5]:
                date = (warned_at or "")[:16].replace("T", " ")
                lines.append(f"`{date}` — +{amount} — *{reason}* (von {mod_name})")
            embed.add_field(name="📋 Verlauf (letzte 5)", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="📋 Verlauf", value="Keine Verwarnungen.", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="clearwarns")
    @commands.has_permissions(administrator=True)
    async def clearwarns_cmd(self, ctx: commands.Context, member: discord.Member):
        """Löscht alle Verwarnungen eines Nutzers — %clearwarns @nutzer"""
        total = _total_warns(member.id)
        if total == 0:
            await ctx.send(f"ℹ️ {member.mention} hat keine Verwarnungen.")
            return
        _clear_warns(member.id)
        await ctx.send(f"✅ Alle **{total}** Verwarnungen von **{member.display_name}** wurden gelöscht.")
        await send_log(
            self.bot,
            "🗑️ Verwarnungen gelöscht",
            f"👤  **Nutzer:** {member.mention} (`{member.id}`)\n"
            f"👮  **Von:** {ctx.author}\n"
            f"⚠️  **Gelöschte Warns:** {total}",
            discord.Color.from_rgb(100, 100, 100),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(WarnsCog(bot))
