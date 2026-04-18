import asyncio
import os
import sys
import threading

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def start_webpanel(bot_instance, loop):
    """Startet das Web-Dashboard in einem separaten Thread."""
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "web"))
    from app import app
    app.config["BOT"]  = bot_instance
    app.config["LOOP"] = loop
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

from database import Database
from utils import base_name, is_name_protected, send_log

load_dotenv()

COGS = [
    "cogs.economy",
    "cogs.tictactoe",
    "cogs.slots",
    "cogs.blackjack",
    "cogs.roulette",
    "cogs.minigames",
    "cogs.levels",
    "cogs.welcome",
    "cogs.streak",
    "cogs.ranks",
    "cogs.templates",
    "cogs.polls",
    "cogs.stats_tracker",
    "cogs.knast",
    "cogs.kummerkasten",
    "cogs.verifizierung",
    "cogs.gif_limit",
]


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True  # Pflicht für Prefix-Commands
    intents.members = True           # Pflicht für on_member_join
    intents.voice_states = True      # Pflicht für Voice-Tracking

    bot = commands.Bot(command_prefix="%", intents=intents, help_command=None)
    bot.db = Database()  # type: ignore[attr-defined]
    return bot


bot = create_bot()


@tasks.loop(hours=1)
async def hourly_status():
    """Stündlicher Online-Status-Log."""
    member_count = sum(g.member_count for g in bot.guilds)
    await send_log(
        bot,
        "🟢 Bot Online",
        f"🖥️  **Server:** {len(bot.guilds)}\n"
        f"👥  **Mitglieder:** {member_count}\n"
        f"⚡  **Status:** Alle Systeme normal",
        discord.Color.from_rgb(34, 197, 94),
    )


@bot.event
async def on_ready():
    print(f"✅  Eingeloggt als {bot.user}  (ID: {bot.user.id})")
    print(f"📡  Verbunden mit {len(bot.guilds)} Server(n)")

    # Slash-Commands registrieren
    synced = await bot.tree.sync()
    print(f"⚡  {len(synced)} Slash-Commands synchronisiert")

    # Alle Server-Mitglieder in die Datenbank eintragen
    count = 0
    for guild in bot.guilds:
        async for member in guild.fetch_members(limit=None):
            if not member.bot:
                await bot.db.get_user(member.id, base_name(member.display_name))
                await bot.db.set_name_protected(member.id, is_name_protected(member))
                count += 1
    print(f"👥  {count} Mitglieder synchronisiert")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing,
            name="IN LOVE WITH ⛧༒ ARIEL༒⛧",
        )
    )

    if not hourly_status.is_running():
        hourly_status.start()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
        return
    import traceback
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    await send_log(
        bot,
        "❌ Befehlsfehler",
        f"💬  **Befehl:** `{ctx.message.content[:100]}`\n"
        f"👤  **Nutzer:** {ctx.author} (`{ctx.author.id}`)\n"
        f"📍  **Kanal:** #{ctx.channel.name}\n"
        f"⚠️  **Fehler:** `{type(error).__name__}: {str(error)[:150]}`\n"
        f"```py\n{tb[-400:]}\n```",
        discord.Color.from_rgb(239, 68, 68),
    )

@bot.event
async def on_member_join(member: discord.Member):
    if not member.bot:
        await bot.db.get_user(member.id, base_name(member.display_name))
        await bot.db.set_name_protected(member.id, is_name_protected(member))

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if after.bot:
        return
    # DB-Schutzflag aktualisieren wenn sich Rollen geändert haben
    if before.roles != after.roles:
        await bot.db.set_name_protected(after.id, is_name_protected(after))
    if before.display_name != after.display_name:
        await bot.db.get_user(after.id, base_name(after.display_name))


async def main():
    # Web-Dashboard starten (Bot + Loop übergeben für Cog-Steuerung)
    loop = asyncio.get_event_loop()
    web_thread = threading.Thread(target=start_webpanel, args=(bot, loop), daemon=True)
    web_thread.start()
    print("🌐  Web-Dashboard: http://127.0.0.1:5000")

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN fehlt! Erstelle eine .env-Datei mit DISCORD_TOKEN=<dein_token>"
        )

    async with bot:
        await bot.db.init()
        for cog in COGS:
            await bot.load_extension(cog)
            print(f"   ✔ Cog geladen: {cog}")
        try:
            await bot.start(token)
        except discord.LoginFailure:
            print("❌ FEHLER: Token ungültig! Bitte Token zurücksetzen.")
        except discord.PrivilegedIntentsRequired as e:
            print(f"❌ FEHLER: Privileged Intent fehlt im Developer Portal: {e}")
            print("   → Aktiviere: 'Message Content Intent' UND 'Server Members Intent'")
        except Exception as e:
            print(f"❌ UNBEKANNTER FEHLER: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
