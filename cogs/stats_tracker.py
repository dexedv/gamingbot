import discord
from discord.ext import commands


class StatsTrackerCog(commands.Cog, name="StatsTracker"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if ctx.command:
            await self.bot.db.log_command(ctx.command.qualified_name)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        await self.bot.db.log_daily_message()


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsTrackerCog(bot))
