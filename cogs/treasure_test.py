import discord
from discord.ext import commands

TEST_CHANNEL_ID = 1494045465656955000


class TreasureTestCog(commands.Cog, name="TreasureTest"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="treasuretest", hidden=True)
    async def treasure_test(self, ctx: commands.Context):
        if ctx.author.id != 307210134856400908:
            return
        channel = self.bot.get_channel(TEST_CHANNEL_ID)
        if not channel:
            await ctx.send("❌ Channel nicht gefunden.")
            return
        await channel.send("l.treasure")
        await ctx.send(f"✅ `l.treasure` wurde in {channel.mention} gesendet.", delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(TreasureTestCog(bot))
