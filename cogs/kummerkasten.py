import discord
import sqlite3
import os
import sys
from discord.ext import commands

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import send_log

KUMMERKASTEN_CHANNEL_ID = 1494953569097613382
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')


class KummerkastenCog(commands.Cog, name="Kummerkasten"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="kummerkasten", aliases=["kk", "anonym"])
    async def kummerkasten(self, ctx: commands.Context, *, nachricht: str = None):
        """Sendet eine anonyme Nachricht an die Moderation. Nur per DM nutzbar.
        Beispiel: %kummerkasten Ich möchte etwas melden…"""

        # Nur in DMs erlaubt
        if not isinstance(ctx.channel, discord.DMChannel):
            try:
                await ctx.message.delete()
            except Exception:
                pass
            hint = await ctx.send(
                "🔒 Bitte schreib mir diese Nachricht als **Privatnachricht** (DM), "
                "damit deine Anonymität gewahrt bleibt!\n"
                "Klick auf meinen Namen → **Nachricht senden** → `%kummerkasten Dein Text`"
            )
            return

        if not nachricht or not nachricht.strip():
            await ctx.send(
                "📬 **Kummerkasten — Anleitung**\n\n"
                "Schreib einfach:\n"
                "`%kummerkasten Hier dein Text…`\n\n"
                "Deine Nachricht wird **vollständig anonym** an die Moderation weitergeleitet. "
                "Es wird kein Name, kein Account und keine ID gespeichert oder weitergegeben."
            )
            return

        nachricht = nachricht.strip()
        if len(nachricht) > 1800:
            await ctx.send("❌ Die Nachricht ist zu lang (max. 1800 Zeichen).")
            return

        # Zielkanal holen
        channel = self.bot.get_channel(KUMMERKASTEN_CHANNEL_ID)
        if not channel:
            await ctx.send("❌ Der Kummerkasten-Kanal ist gerade nicht erreichbar. Bitte versuche es später.")
            return

        # Anonymes Embed posten
        embed = discord.Embed(
            title="📬 Neue anonyme Nachricht",
            description=nachricht,
            color=discord.Color.from_rgb(168, 85, 247),
        )
        embed.set_footer(text="Diese Nachricht wurde anonym eingereicht · Absender unbekannt")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Der Bot hat keine Berechtigung, in den Kummerkasten-Kanal zu schreiben.")
            return

        # Zähler in DB eintragen + Discord-Log
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO kummerkasten_log DEFAULT VALUES")
            conn.commit()
            total = conn.execute("SELECT COUNT(*) FROM kummerkasten_log").fetchone()[0]
            conn.close()
            await send_log(
                self.bot,
                "📬 Kummerkasten",
                f"📩  **Neue anonyme Nachricht eingegangen**\n"
                f"📊  **Gesamt bisher:** {total}",
            )
        except Exception:
            pass

        # Bestätigung an den Absender (ohne Details)
        confirm = discord.Embed(
            title="✅ Nachricht eingegangen",
            description=(
                "Deine Nachricht wurde **anonym** an die Moderation weitergeleitet.\n\n"
                "Es wurden keinerlei Informationen über dich gespeichert oder weitergegeben."
            ),
            color=discord.Color.from_rgb(34, 197, 94),
        )
        confirm.set_footer(text="Danke, dass du dich meldest.")
        await ctx.send(embed=confirm)


async def setup(bot: commands.Bot):
    await bot.add_cog(KummerkastenCog(bot))
