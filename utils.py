import math
import re
import discord


# ── Benachrichtigungskanal ────────────────────────────────────────────────────

NOTIFY_CHANNEL_ID = 1494057689435869485
LOG_CHANNEL_ID    = 1494676015459471450


def _read_settings() -> dict:
    import json, os as _os, sqlite3
    db_path = _os.path.join(_os.path.dirname(__file__), "data", "gamingbot.db")
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT key, value FROM bot_settings").fetchall()
        conn.close()
        if rows:
            result = {}
            for key, val in rows:
                try:
                    result[key] = json.loads(val)
                except Exception:
                    result[key] = val
            return result
    except Exception:
        pass
    # Fallback: settings.json
    path = _os.path.join(_os.path.dirname(__file__), "settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


async def send_notify(bot, embed) -> None:
    """Sendet Level-Up / Streak-Benachrichtigungen in den dedizierten Kanal."""
    channel_id = _read_settings().get("notify_channel", NOTIFY_CHANNEL_ID)
    channel = bot.get_channel(int(channel_id))
    if channel:
        await channel.send(embed=embed)


async def send_log(bot, title: str, description: str = "", color: discord.Color = None) -> None:
    """Sendet eine Log-Nachricht in den dedizierten Log-Kanal."""
    from datetime import datetime, timezone
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    # Auto-Farbe anhand des Titel-Emojis falls keine angegeben
    if color is None:
        if title.startswith(("✅", "🟢", "📸", "📋", "📨", "📤", "📊")):
            color = discord.Color.from_rgb(34, 197, 94)
        elif title.startswith("❌"):
            color = discord.Color.from_rgb(239, 68, 68)
        elif title.startswith(("🔄", "🔧", "⚠️", "🔒")):
            color = discord.Color.from_rgb(251, 146, 60)
        else:
            color = discord.Color.from_rgb(88, 101, 242)

    avatar_url = bot.user.avatar.url if bot.user and bot.user.avatar else None

    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if description:
        embed.description = description
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.set_footer(
        text="Pink Horizoon Bot · Log-System",
        icon_url=avatar_url,
    )
    try:
        await channel.send(embed=embed)
    except Exception:
        pass


# ── Geschützte Rolle ──────────────────────────────────────────────────────────

PROTECTED_ROLE_ID = 1494612383899975781


def is_name_protected(member) -> bool:
    """True wenn der Nutzer die geschützte Rolle hat (Benutzername nicht ändern)."""
    return any(r.id == PROTECTED_ROLE_ID for r in getattr(member, "roles", []))


# ── Nickname-Hilfsfunktion ────────────────────────────────────────────────────

def base_name(display_name: str) -> str:
    """Entfernt den Streak-Suffix (| 🔥N) aus einem Anzeigenamen."""
    if ' | ' in display_name:
        display_name = display_name[:display_name.rfind(' | ')].strip()
    elif '🔥' in display_name:
        display_name = display_name[:display_name.rfind('🔥')].strip().rstrip('|').strip()
    display_name = re.sub(r'[\s・]*\d*🔥\d*', '', display_name).strip()
    display_name = re.sub(r'\s{2,}', ' ', display_name).strip()
    return display_name


# ── Level-Formeln ─────────────────────────────────────────────────────────────

def level_from_xp(xp: int) -> int:
    """Berechnet Level aus Gesamt-XP (quadratische Skalierung)."""
    return int(math.sqrt(xp / 50))


def xp_for_level(level: int) -> int:
    """Gesamt-XP die benötigt werden um dieses Level zu erreichen."""
    return level * level * 50


def xp_to_next_level(xp: int) -> int:
    """Wie viel XP noch bis zum nächsten Level fehlen."""
    current_level = level_from_xp(xp)
    return xp_for_level(current_level + 1) - xp


def xp_in_current_level(xp: int) -> int:
    """XP-Fortschritt innerhalb des aktuellen Levels."""
    current_level = level_from_xp(xp)
    return xp - xp_for_level(current_level)


def xp_needed_for_level(level: int) -> int:
    """Wie viel XP ein Level insgesamt kostet (von level zu level+1)."""
    return xp_for_level(level + 1) - xp_for_level(level)


def daily_coins(level: int) -> int:
    """Tägliche Münzen steigen mit dem Level (+10 pro Level, max 1000)."""
    return min(200 + level * 10, 1000)


# ── Level-Rang ────────────────────────────────────────────────────────────────

def level_rank(level: int) -> tuple[str, str]:
    """Gibt (Emoji, Rang-Name) zurück."""
    if level < 5:
        return "🌱", "Anfänger"
    if level < 10:
        return "🥉", "Bronze"
    if level < 15:
        return "🥈", "Silber"
    if level < 20:
        return "🥇", "Gold"
    if level < 30:
        return "💎", "Diamant"
    if level < 50:
        return "🔥", "Meister"
    return "👑", "Legende"


def xp_bar(xp: int, width: int = 10) -> str:
    """Erstellt einen visuellen XP-Fortschrittsbalken."""
    level     = level_from_xp(xp)
    current   = xp_in_current_level(xp)
    needed    = xp_needed_for_level(level)
    filled    = int(current / needed * width)
    bar       = "█" * filled + "░" * (width - filled)
    return f"`{bar}` {current:,} / {needed:,} XP"


# ── Level-Up Embed ────────────────────────────────────────────────────────────

def level_up_embed(user: discord.Member, old_level: int, new_level: int) -> discord.Embed:
    emoji, rank = level_rank(new_level)
    embed = discord.Embed(
        title=f"🎉  Level Up!  {emoji}",
        description=(
            f"**{user.display_name}** ist auf **Level {new_level}** gestiegen!\n"
            f"Rang: **{rank}**\n\n"
            f"💰 Neue tägliche Münzen: **{daily_coins(new_level):,}**\n"
            f"*(war: {daily_coins(old_level):,})*"
        ),
        color=discord.Color.from_rgb(255, 215, 0),
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    return embed
