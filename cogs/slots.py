import asyncio
import discord
import random
from discord.ext import commands

# Symbol | weight | 3-of-a-kind multiplier | 2-of-a-kind multiplier
REELS: list[tuple[str, int, float, float]] = [
    ("🍒", 30, 3.0,  1.5),
    ("🍋", 25, 4.0,  1.5),
    ("🍊", 20, 5.0,  1.5),
    ("⭐", 12, 8.0,  2.0),
    ("💎",  8, 15.0, 2.5),
    ("7️⃣",  4, 25.0, 3.0),
    ("🎰",  1, 50.0, 5.0),
]

SYMBOLS = [r[0] for r in REELS]
WEIGHTS = [r[1] for r in REELS]
THREE_X = {r[0]: r[2] for r in REELS}
TWO_X   = {r[0]: r[3] for r in REELS}

# Multiplikator-Walze: Wert | Gewicht
# 1x=35% · 2x=25% · 3x=18% · 4x=10% · 5x=6% · 6x=3% · 7x=1.5% · 8x=1% · 9x=0.5%
MULTI_VALUES  = [1,  2,  3,  4,  5,  6, 7, 8, 9]
MULTI_WEIGHTS = [70, 50, 36, 20, 12, 6, 3, 2, 1]

MIN_BET =   10
MAX_BET = 1_000

# Animationsfarben
ANIM_COLORS = [
    discord.Color.from_rgb(255, 214, 0),   # gelb
    discord.Color.from_rgb(255, 165, 0),   # orange
    discord.Color.from_rgb(255, 120, 0),   # dunkelorange
    discord.Color.from_rgb(220,  80, 0),   # tieforange
    discord.Color.from_rgb(180,  50, 220), # lila (Multiplikator)
]


def spin_result() -> tuple[list[str], int]:
    symbols = random.choices(SYMBOLS, weights=WEIGHTS, k=3)
    multi   = random.choices(MULTI_VALUES, weights=MULTI_WEIGHTS, k=1)[0]
    return symbols, multi


def calculate(result: list[str], multi: int, bet: int) -> tuple[float, int]:
    s0, s1, s2 = result
    if s0 == s1 == s2:
        base_mult = THREE_X[s0]
    elif s0 == s1:
        base_mult = TWO_X[s0]
    elif s1 == s2:
        base_mult = TWO_X[s1]
    else:
        base_mult = 0.0
    total_mult = base_mult * multi if base_mult > 0 else 0.0
    return total_mult, int(bet * total_mult)


def machine(s0: str, s1: str, s2: str, multi: str, spinning: bool = False) -> str:
    """Erstellt die Slot-Machine Anzeige."""
    spin_hint = "  🔄 dreht sich..." if spinning else ""
    return (
        f"```\n"
        f"╔══════════════════════╗\n"
        f"║  {s0}   {s1}   {s2}   ✖ {multi}  ║\n"
        f"╚══════════════════════╝\n"
        f"```"
        + (f"\n*{spin_hint}*" if spinning else "")
    )


class SlotsView(discord.ui.View):
    def __init__(self, cog, user: discord.Member, einsatz: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        self.einsatz = einsatz
        self.played = False

    @discord.ui.button(label="🎰  Drehen!", style=discord.ButtonStyle.success)
    async def spin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Das ist nicht dein Spiel!", ephemeral=True)
            return
        if self.played:
            await interaction.response.send_message("Du hast schon gespielt!", ephemeral=True)
            return

        self.played = True
        button.disabled = True

        db = self.cog.bot.db
        coins = await db.get_coins(self.user.id)
        if coins < self.einsatz:
            await interaction.response.edit_message(
                content=f"❌ Nicht genug Münzen! Du hast nur **{coins:,}** Münzen.",
                view=self,
            )
            return

        await db.update_coins(self.user.id, -self.einsatz)
        await db.add_spin(self.user.id)

        symbols, multi = spin_result()
        total_mult, winnings = calculate(symbols, multi, self.einsatz)

        # ── Animation ─────────────────────────────────────────────────────────
        await interaction.response.defer()

        spin_frames = [
            ("❓", "❓", "❓", "?", True,  ANIM_COLORS[0], "🎰  Dreht sich..."),
            (*random.choices(SYMBOLS, k=3), "?", True,  ANIM_COLORS[1], "🎰  Dreht sich..."),
            (symbols[0], "❓", "❓",       "?", False, ANIM_COLORS[2], f"🎰  Walze 1 › {symbols[0]}"),
            (symbols[0], symbols[1], "❓", "?", False, ANIM_COLORS[3], f"🎰  Walze 2 › {symbols[1]}"),
            (symbols[0], symbols[1], symbols[2], "?", False, ANIM_COLORS[3], f"🎰  Walze 3 › {symbols[2]}"),
        ]

        for s0, s1, s2, m, spinning, color, title in spin_frames:
            e = discord.Embed(title=title, color=color)
            e.description = machine(s0, s1, s2, m, spinning)
            e.set_footer(text=f"💰 Einsatz: {self.einsatz:,} Münzen  •  🎮 {self.user.display_name}")
            await interaction.edit_original_response(embed=e, view=self)
            await asyncio.sleep(0.8)

        # Multiplikator enthüllen
        e = discord.Embed(title=f"✖️  Multiplikator: {multi}×", color=ANIM_COLORS[4])
        e.description = machine(*symbols, f"{multi}×")
        e.set_footer(text=f"💰 Einsatz: {self.einsatz:,} Münzen  •  🎮 {self.user.display_name}")
        await interaction.edit_original_response(embed=e, view=self)
        await asyncio.sleep(1.2)

        # ── Ergebnis ──────────────────────────────────────────────────────────
        xp_gain = 10
        if winnings > 0:
            await db.update_coins(self.user.id, winnings)
            xp_gain += 5
            profit = winnings - self.einsatz
            if total_mult >= 450:
                banner = "🌟  MEGA JACKPOT!!!"
                result_text = f"**+{profit:,} Münzen** — unglaublich!"
            elif total_mult >= 50:
                banner = "🌟  JACKPOT!!!"
                result_text = f"**+{profit:,} Münzen**"
            elif total_mult >= 25:
                banner = "🔥  SIEBEN HOCH!"
                result_text = f"**+{profit:,} Münzen**"
            else:
                banner = "🎉  GEWONNEN!"
                result_text = f"**+{profit:,} Münzen** (×{total_mult:.1f})"
            color = discord.Color.from_rgb(255, 200, 0)
        else:
            banner = "💸  Verloren!"
            result_text = f"**-{self.einsatz:,} Münzen**"
            color = discord.Color.from_rgb(200, 40, 40)

        old_level, new_level = await db.add_xp(self.user.id, xp_gain)
        new_coins = await db.get_coins(self.user.id)

        embed = discord.Embed(title=f"🎰  Spielautomat  —  {banner}", color=color)
        embed.description = machine(*symbols, f"{multi}×")
        embed.add_field(name="💰 Einsatz",       value=f"{self.einsatz:,} Münzen", inline=True)
        embed.add_field(name="✖️ Multiplikator",  value=f"{multi}×",               inline=True)
        embed.add_field(name="📊 Gesamt-Faktor",  value=f"×{total_mult:.1f}",      inline=True)
        embed.add_field(name="─" * 28,            value=result_text,               inline=False)
        embed.add_field(name="💳 Neues Guthaben", value=f"{new_coins:,} Münzen",   inline=True)
        embed.set_footer(text=f"🎮 {self.user.display_name}")
        embed.set_thumbnail(url=self.user.display_avatar.url)

        self.play_again_btn.disabled = False
        await interaction.edit_original_response(content=None, embed=embed, view=self)

        if new_level > old_level:
            from utils import level_up_embed
            await interaction.followup.send(embed=level_up_embed(self.user, old_level, new_level))

    @discord.ui.button(label="🔄  Nochmal spielen", style=discord.ButtonStyle.success,
                       disabled=True, row=1)
    async def play_again_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        coins = await self.cog.bot.db.get_coins(self.user.id)
        if coins < self.einsatz:
            await interaction.response.send_message(
                f"❌ Nicht genug Münzen! Du hast nur **{coins:,}** Münzen.", ephemeral=True
            )
            return
        button.disabled = True
        new_view = SlotsView(self.cog, self.user, self.einsatz)
        embed = discord.Embed(
            title="🎰  Spielautomat",
            description=f"**Einsatz: {self.einsatz:,} Münzen**\nGuthaben: {coins:,} Münzen\n\nDrücke den Button!",
            color=discord.Color.from_rgb(255, 200, 0),
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.set_footer(text=f"🎮 {self.user.display_name}  •  Viel Glück!")
        await interaction.response.edit_message(embed=embed, view=new_view)


class SlotsCog(commands.Cog, name="Slots"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="slots", aliases=["slot", "spin"])
    async def slots(self, ctx: commands.Context, einsatz: int):
        """Spiele am Spielautomaten – %slots <einsatz>"""
        await self.bot.db.get_user(ctx.author.id, ctx.author.display_name)

        if einsatz < MIN_BET:
            await ctx.send(f"❌ Mindest-Einsatz ist **{MIN_BET} Münzen**!")
            return
        if einsatz > MAX_BET:
            await ctx.send(f"❌ Maximal-Einsatz ist **{MAX_BET} Münzen**!")
            return

        coins = await self.bot.db.get_coins(ctx.author.id)
        if coins < einsatz:
            await ctx.send(f"❌ Nicht genug Münzen! Du hast **{coins:,}** Münzen.")
            return

        embed = discord.Embed(
            title="🎰  Spielautomat",
            description=(
                f"**Einsatz: {einsatz:,} Münzen**\n"
                f"Guthaben: {coins:,} Münzen\n\n"
                f"Drücke den Button und dreh die Walzen!"
            ),
            color=discord.Color.from_rgb(255, 200, 0),
        )
        embed.add_field(
            name="🍀 Auszahlungstabelle",
            value=(
                "🍒🍒🍒 `= 3×`  ·  🍋🍋🍋 `= 4×`  ·  🍊🍊🍊 `= 5×`\n"
                "⭐⭐⭐ `= 8×`  ·  💎💎💎 `= 15×`  ·  7️⃣7️⃣7️⃣ `= 25×`\n"
                "🎰🎰🎰 `= JACKPOT 50×!`\n"
                "*Zwei gleiche Symbole geben kleinere Auszahlung*"
            ),
            inline=False,
        )
        embed.add_field(
            name="✖️ Multiplikator-Walze",
            value=(
                "`1×` 35%  ·  `2×` 25%  ·  `3×` 18%  ·  `4×` 10%\n"
                "`5×` 6%  ·  `6×` 3%  ·  `7×` 1.5%  ·  `8×` 1%  ·  **`9×` 0.5%**"
            ),
            inline=False,
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"🎮 {ctx.author.display_name}  •  Viel Glück!")

        view = SlotsView(self, ctx.author, einsatz)
        await ctx.send(embed=embed, view=view)

    @slots.error
    async def slots_error(self, ctx: commands.Context, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("❌ Benutzung: `%slots <einsatz>` — z.B. `%slots 100`")


async def setup(bot: commands.Bot):
    await bot.add_cog(SlotsCog(bot))
