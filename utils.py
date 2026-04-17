import math
import discord


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
