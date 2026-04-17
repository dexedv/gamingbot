import discord
from discord.ext import commands

WELCOME_CHANNEL_ID  = 1019608622663209000
RULES_CHANNEL_ID    = 1019184912110211103
ROLES_CHANNEL_ID    = 1019594993226219610


class WelcomeCog(commands.Cog, name="Welcome"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = self.bot.get_channel(WELCOME_CHANNEL_ID)
        if channel is None:
            return

        embed = discord.Embed(
            title=f"👋  Willkommen auf {member.guild.name}!",
            description=(
                f"Schön dass du da bist, {member.mention}! 🎉\n"
                f"Du bist unser **{member.guild.member_count}. Mitglied** — herzlich willkommen!"
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_image(url=member.guild.banner.url if member.guild.banner else None)
        embed.add_field(
            name="📜  Regeln",
            value=f"Lies unsere Regeln durch bevor du loslegst!\n<#{RULES_CHANNEL_ID}>",
            inline=True,
        )
        embed.add_field(
            name="🎭  Rollen",
            value=f"Such dir deine Rollen aus!\n<#{ROLES_CHANNEL_ID}>",
            inline=True,
        )
        embed.add_field(
            name="🤝  Paten-System",
            value=f"Neu hier? Wir haben ein **Paten-System**!\nEin erfahrenes Mitglied begleitet dich durch den Server.\nEinfach ein Ticket öffnen: <#1494054503647805562>",
            inline=False,
        )
        embed.set_footer(
            text=f"{member.guild.name}  •  Viel Spaß!",
            icon_url=member.guild.icon.url if member.guild.icon else None,
        )

        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))
