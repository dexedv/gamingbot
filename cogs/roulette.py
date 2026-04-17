import discord
import random
from discord.ext import commands

class RoulettePlayAgainView(discord.ui.View):
    def __init__(self, cog, user: discord.Member, einsatz: int, bet_type: str, bet_name: str):
        super().__init__(timeout=60)
        self.cog      = cog
        self.user     = user
        self.einsatz  = einsatz
        self.bet_type = bet_type
        self.bet_name = bet_name

    @discord.ui.button(label="🔄  Nochmal spielen", style=discord.ButtonStyle.success)
    async def play_again_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        coins = await self.cog.bot.db.get_coins(self.user.id)
        if coins < self.einsatz:
            await interaction.response.send_message(
                f"❌ Nicht genug Münzen! Du hast **{coins:,}** Münzen.", ephemeral=True
            )
            return
        button.disabled = True

        number      = random.randint(0, 36)
        won, mult   = check_win(self.bet_type, number)
        color_emoji = number_color(number)
        db          = self.cog.bot.db

        await db.update_coins(self.user.id, -self.einsatz)

        if won:
            payout = int(self.einsatz * mult)
            profit = payout - self.einsatz
            await db.update_coins(self.user.id, payout)
            await db.add_win(self.user.id)
            title  = "🎡  Roulette  —  Gewonnen! 🎉"
            result = f"**+{profit:,} Münzen** (×{mult:.0f})"
            color  = WIN_COLOR
            xp_gain = 18
        else:
            await db.add_loss(self.user.id)
            title  = "🎡  Roulette  —  Verloren! 💸"
            result = f"**-{self.einsatz:,} Münzen**"
            color  = LOSE_COLOR
            xp_gain = 10

        old_level, new_level = await db.add_xp(self.user.id, xp_gain)
        new_coins = await db.get_coins(self.user.id)
        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="🎯  Ergebnis",     value=f"**{color_emoji} {number}**",  inline=True)
        embed.add_field(name="🎲  Deine Wette",  value=self.bet_name,                  inline=True)
        embed.add_field(name="📊  Auszahlung",   value=f"×{mult:.0f}",                 inline=True)
        embed.add_field(name="─" * 28,           value=result,                         inline=False)
        embed.add_field(name="💳  Guthaben",     value=f"{new_coins:,} Münzen",        inline=True)
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.set_footer(text=f"💰 Einsatz: {self.einsatz:,} Münzen  •  🎮 {self.user.display_name}")
        new_view = RoulettePlayAgainView(self.cog, self.user, self.einsatz, self.bet_type, self.bet_name)
        await interaction.response.edit_message(embed=embed, view=new_view)

        if new_level > old_level:
            from utils import level_up_embed, send_notify
            await send_notify(self.cog.bot, level_up_embed(self.user, old_level, new_level))

# Roulette-Zahlen Farben (europäisches Roulette)
RED_NUMS = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}

WIN_COLOR  = discord.Color.from_rgb(87, 242, 135)
LOSE_COLOR = discord.Color.from_rgb(200, 40, 40)


def number_color(n: int) -> str:
    if n == 0:
        return "🟢"
    return "🔴" if n in RED_NUMS else "⚫"


def parse_bet(arg: str) -> tuple[str, str] | None:
    """Gibt (bet_type, display_name) zurück oder None wenn ungültig."""
    a = arg.lower().strip()
    if a in ("rot", "red", "r"):
        return "rot", "🔴 Rot"
    if a in ("schwarz", "black", "s", "b"):
        return "schwarz", "⚫ Schwarz"
    if a in ("gerade", "even", "g"):
        return "gerade", "🔵 Gerade"
    if a in ("ungerade", "odd", "u"):
        return "ungerade", "🟣 Ungerade"
    if a in ("1-12", "erste"):
        return "1-12", "1️⃣ Erste Dozen (1–12)"
    if a in ("13-24", "zweite"):
        return "13-24", "2️⃣ Zweite Dozen (13–24)"
    if a in ("25-36", "dritte"):
        return "25-36", "3️⃣ Dritte Dozen (25–36)"
    try:
        n = int(a)
        if 0 <= n <= 36:
            return f"num:{n}", f"{number_color(n)} Nummer **{n}**"
    except ValueError:
        pass
    return None


def check_win(bet_type: str, number: int) -> tuple[bool, float]:
    """Gibt (gewonnen, multiplikator) zurück."""
    if bet_type == "rot":
        return number in RED_NUMS and number != 0, 2.0
    if bet_type == "schwarz":
        return number not in RED_NUMS and number != 0, 2.0
    if bet_type == "gerade":
        return number % 2 == 0 and number != 0, 2.0
    if bet_type == "ungerade":
        return number % 2 == 1, 2.0
    if bet_type == "1-12":
        return 1 <= number <= 12, 3.0
    if bet_type == "13-24":
        return 13 <= number <= 24, 3.0
    if bet_type == "25-36":
        return 25 <= number <= 36, 3.0
    if bet_type.startswith("num:"):
        target = int(bet_type.split(":")[1])
        return number == target, 36.0
    return False, 0.0


class RouletteCog(commands.Cog, name="Roulette"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="roulette", aliases=["rl"])
    async def roulette(self, ctx: commands.Context, einsatz: int, wette: str):
        """Spiele Roulette — %roulette <einsatz> <wette>"""
        await self.bot.db.get_user(ctx.author.id, ctx.author.display_name)

        if einsatz < 10:
            await ctx.send("❌ Mindest-Einsatz ist **10 Münzen**!")
            return
        if einsatz > 5000:
            await ctx.send("❌ Maximal-Einsatz ist **5000 Münzen**!")
            return

        parsed = parse_bet(wette)
        if parsed is None:
            embed = discord.Embed(
                title="🎡  Roulette  —  Ungültige Wette",
                description=(
                    "**Verfügbare Wetten:**\n"
                    "`rot` / `schwarz` — 2×\n"
                    "`gerade` / `ungerade` — 2×\n"
                    "`1-12` / `13-24` / `25-36` — 3×\n"
                    "`0`–`36` (Zahl) — **36×**\n\n"
                    "Beispiel: `%roulette 100 rot` oder `%roulette 50 17`"
                ),
                color=discord.Color.from_rgb(180, 40, 40),
            )
            await ctx.send(embed=embed)
            return

        coins = await self.bot.db.get_coins(ctx.author.id)
        if coins < einsatz:
            await ctx.send(f"❌ Nicht genug Münzen! Du hast **{coins:,}** Münzen.")
            return

        bet_type, bet_name = parsed
        number  = random.randint(0, 36)
        won, mult = check_win(bet_type, number)
        color_emoji = number_color(number)

        await self.bot.db.update_coins(ctx.author.id, -einsatz)

        if won:
            payout = int(einsatz * mult)
            profit = payout - einsatz
            await self.bot.db.update_coins(ctx.author.id, payout)
            await self.bot.db.add_win(ctx.author.id)
            title  = "🎡  Roulette  —  Gewonnen! 🎉"
            result = f"**+{profit:,} Münzen** (×{mult:.0f})"
            color  = WIN_COLOR
            xp_gain = 18
        else:
            await self.bot.db.add_loss(ctx.author.id)
            title  = "🎡  Roulette  —  Verloren! 💸"
            result = f"**-{einsatz:,} Münzen**"
            color  = LOSE_COLOR
            xp_gain = 10

        old_level, new_level = await self.bot.db.add_xp(ctx.author.id, xp_gain)
        new_coins = await self.bot.db.get_coins(ctx.author.id)

        embed = discord.Embed(title=title, color=color)
        embed.add_field(
            name="🎯  Ergebnis",
            value=f"**{color_emoji} {number}**",
            inline=True,
        )
        embed.add_field(name="🎲  Deine Wette", value=bet_name,    inline=True)
        embed.add_field(name="📊  Auszahlung",  value=f"×{mult:.0f}", inline=True)
        embed.add_field(name="─" * 28,          value=result,       inline=False)
        embed.add_field(name="💳  Guthaben",    value=f"{new_coins:,} Münzen", inline=True)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"💰 Einsatz: {einsatz:,} Münzen  •  🎮 {ctx.author.display_name}")
        view = RoulettePlayAgainView(self, ctx.author, einsatz, bet_type, bet_name)
        await ctx.send(embed=embed, view=view)

        if new_level > old_level:
            from utils import level_up_embed, send_notify
            await send_notify(self.bot, level_up_embed(ctx.author, old_level, new_level))

    @roulette.error
    async def rl_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                "❌ Benutzung: `%roulette <einsatz> <wette>`\n"
                "Wetten: `rot` `schwarz` `gerade` `ungerade` `1-12` `13-24` `25-36` oder Zahl `0-36`"
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Einsatz muss eine Zahl sein!")


async def setup(bot: commands.Bot):
    await bot.add_cog(RouletteCog(bot))
