import json
import os
import discord
from discord.ext import commands

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '..', 'settings.json')

DEFAULTS = {
    "welcome_enabled":       True,
    "welcome_channel":       1019608622663209000,
    "welcome_title":         "👋 Willkommen auf {guild}!",
    "welcome_description":   "Schön dass du da bist, {mention}! 🎉\nDu bist unser **{count}. Mitglied** — herzlich willkommen!",
    "welcome_color":         "#5865f2",
    "welcome_rules_channel": 1019184912110211103,
    "welcome_roles_channel": 1019594993226219610,
    "welcome_paten_channel": 1494054503647805562,
    "welcome_footer":        "{guild} • Viel Spaß!",
    "welcome_show_banner":   True,
}


def _load() -> dict:
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return {**DEFAULTS, **json.load(f)}
    except Exception:
        return dict(DEFAULTS)


def _hex_color(hex_str: str) -> discord.Color:
    try:
        h = hex_str.lstrip('#')
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return discord.Color.from_rgb(r, g, b)
    except Exception:
        return discord.Color.blurple()


class WelcomeCog(commands.Cog, name="Welcome"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        s = _load()
        if not s.get("welcome_enabled", True):
            return
        channel = self.bot.get_channel(int(s["welcome_channel"]))
        if channel is None:
            return

        def fmt(text: str) -> str:
            return str(text).format(
                mention=member.mention,
                guild=member.guild.name,
                count=member.guild.member_count,
                username=member.display_name,
            )

        embed = discord.Embed(
            title=fmt(s["welcome_title"]),
            description=fmt(s["welcome_description"]),
            color=_hex_color(s["welcome_color"]),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if s.get("welcome_show_banner") and member.guild.banner:
            embed.set_image(url=member.guild.banner.url)

        embed.add_field(
            name="📜  Regeln",
            value=f"Lies unsere Regeln durch bevor du loslegst!\n<#{int(s['welcome_rules_channel'])}>",
            inline=True,
        )
        embed.add_field(
            name="🎭  Rollen",
            value=f"Such dir deine Rollen aus!\n<#{int(s['welcome_roles_channel'])}>",
            inline=True,
        )
        embed.add_field(
            name="🤝  Paten-System",
            value=f"Neu hier? Wir haben ein **Paten-System**!\nEin erfahrenes Mitglied begleitet dich.\nTicket öffnen: <#{int(s['welcome_paten_channel'])}>",
            inline=False,
        )
        embed.set_footer(
            text=fmt(s["welcome_footer"]),
            icon_url=member.guild.icon.url if member.guild.icon else None,
        )
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
