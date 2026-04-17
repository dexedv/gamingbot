import discord
import random
from discord.ext import commands

WIN_COLOR  = discord.Color.from_rgb(87, 242, 135)
LOSE_COLOR = discord.Color.from_rgb(200, 40, 40)
TIE_COLOR  = discord.Color.from_rgb(180, 180, 180)

DICE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]


# ══════════════════════════════════════════════════════════════
#  COINFLIP
# ══════════════════════════════════════════════════════════════

class CoinflipView(discord.ui.View):
    def __init__(self, cog, user: discord.Member, einsatz: int):
        super().__init__(timeout=60)
        self.cog    = cog
        self.user   = user
        self.einsatz = einsatz
        self.played = False

    async def resolve(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        if self.played:
            return
        self.played = True

        for child in self.children:
            child.disabled = True

        result  = random.choice(["kopf", "zahl"])
        won     = choice == result
        symbols = {"kopf": "🪙 KOPF", "zahl": "💿 ZAHL"}
        db      = self.cog.bot.db

        await db.update_coins(self.user.id, -self.einsatz)

        if won:
            await db.update_coins(self.user.id, self.einsatz * 2)
            await db.add_win(self.user.id)
            title  = "🪙  Coinflip  —  Gewonnen! 🎉"
            extra  = f"**+{self.einsatz:,} Münzen**"
            color  = WIN_COLOR
            xp_gain = 10
        else:
            await db.add_loss(self.user.id)
            title  = "🪙  Coinflip  —  Verloren! 💸"
            extra  = f"**-{self.einsatz:,} Münzen**"
            color  = LOSE_COLOR
            xp_gain = 5

        old_level, new_level = await db.add_xp(self.user.id, xp_gain)
        new_coins = await db.get_coins(self.user.id)

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="🎯  Deine Wahl",   value=symbols[choice], inline=True)
        embed.add_field(name="🪙  Ergebnis",      value=symbols[result], inline=True)
        embed.add_field(name="─" * 28,            value=extra,           inline=False)
        embed.add_field(name="💳  Guthaben",      value=f"{new_coins:,} Münzen", inline=True)
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.set_footer(text=f"💰 Einsatz: {self.einsatz:,} Münzen  •  🎮 {self.user.display_name}")
        self.play_again_btn.disabled = False
        self.stop()
        await interaction.response.edit_message(embed=embed, view=self)

        if new_level > old_level:
            from utils import level_up_embed
            await interaction.followup.send(embed=level_up_embed(self.user, old_level, new_level))

    @discord.ui.button(label="🪙 Kopf", style=discord.ButtonStyle.primary)
    async def kopf(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.resolve(interaction, "kopf")

    @discord.ui.button(label="💿 Zahl", style=discord.ButtonStyle.secondary)
    async def zahl(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.resolve(interaction, "zahl")

    @discord.ui.button(label="🔄  Nochmal spielen", style=discord.ButtonStyle.success,
                       disabled=True, row=1)
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
        new_view = CoinflipView(self.cog, self.user, self.einsatz)
        embed = discord.Embed(
            title="🪙  Coinflip",
            description=f"**Einsatz: {self.einsatz:,} Münzen**\nWähle Kopf oder Zahl!",
            color=discord.Color.from_rgb(255, 200, 0),
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.set_footer(text=f"🎮 {self.user.display_name}  •  Gewinn: 2×")
        await interaction.response.edit_message(embed=embed, view=new_view)


# ══════════════════════════════════════════════════════════════
#  WÜRFEL
# ══════════════════════════════════════════════════════════════

class DiceView(discord.ui.View):
    def __init__(self, cog, user: discord.Member, einsatz: int):
        super().__init__(timeout=60)
        self.cog     = cog
        self.user    = user
        self.einsatz = einsatz
        self.played  = False

    @discord.ui.button(label="🎲  Würfeln!", style=discord.ButtonStyle.success)
    async def roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        if self.played:
            return
        self.played = True
        button.disabled = True

        p1, p2 = random.randint(1,6), random.randint(1,6)
        b1, b2 = random.randint(1,6), random.randint(1,6)
        ptotal = p1 + p2
        btotal = b1 + b2

        db = self.cog.bot.db
        await db.update_coins(self.user.id, -self.einsatz)

        if ptotal > btotal:
            await db.update_coins(self.user.id, self.einsatz * 2)
            await db.add_win(self.user.id)
            title = "🎲  Würfeln  —  Du gewinnst! 🎉"
            extra = f"**+{self.einsatz:,} Münzen**"
            color = WIN_COLOR
            xp_gain = 13
        elif ptotal < btotal:
            await db.add_loss(self.user.id)
            title = "🎲  Würfeln  —  Bot gewinnt! 💸"
            extra = f"**-{self.einsatz:,} Münzen**"
            color = LOSE_COLOR
            xp_gain = 8
        else:
            await db.update_coins(self.user.id, self.einsatz)
            await db.add_draw(self.user.id)
            title = "🎲  Würfeln  —  Unentschieden! 🤝"
            extra = "Einsatz zurück  —  **±0 Münzen**"
            color = TIE_COLOR
            xp_gain = 8

        old_level, new_level = await db.add_xp(self.user.id, xp_gain)
        new_coins = await db.get_coins(self.user.id)

        embed = discord.Embed(title=title, color=color)
        embed.add_field(
            name=f"🙋  Du  —  **{ptotal}**",
            value=f"{DICE_FACES[p1-1]}  {DICE_FACES[p2-1]}",
            inline=True,
        )
        embed.add_field(
            name=f"🤖  Bot  —  **{btotal}**",
            value=f"{DICE_FACES[b1-1]}  {DICE_FACES[b2-1]}",
            inline=True,
        )
        embed.add_field(name="─" * 28,       value=extra,               inline=False)
        embed.add_field(name="💳  Guthaben", value=f"{new_coins:,} Münzen", inline=True)
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.set_footer(text=f"💰 Einsatz: {self.einsatz:,} Münzen  •  🎮 {self.user.display_name}")
        self.play_again_btn.disabled = False
        self.stop()
        await interaction.response.edit_message(embed=embed, view=self)

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
                f"❌ Nicht genug Münzen! Du hast **{coins:,}** Münzen.", ephemeral=True
            )
            return
        button.disabled = True
        new_view = DiceView(self.cog, self.user, self.einsatz)
        embed = discord.Embed(
            title="🎲  Würfelduell",
            description=f"**Einsatz: {self.einsatz:,} Münzen**\nBeide würfeln 2 Würfel!",
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.set_footer(text=f"🎮 {self.user.display_name}  •  Gewinn: 2×")
        await interaction.response.edit_message(embed=embed, view=new_view)


# ══════════════════════════════════════════════════════════════
#  HIGHER OR LOWER
# ══════════════════════════════════════════════════════════════

class HiLoView(discord.ui.View):
    def __init__(self, cog, user: discord.Member, einsatz: int, current: int, streak: int = 0):
        super().__init__(timeout=60)
        self.cog     = cog
        self.user    = user
        self.einsatz = einsatz
        self.current = current
        self.streak  = streak
        self.done    = False

    def _multiplier(self) -> float:
        return round(1.5 ** self.streak, 2)

    async def guess(self, interaction: discord.Interaction, higher: bool):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        if self.done:
            return

        next_card = random.randint(1, 13)
        correct   = (higher and next_card > self.current) or (not higher and next_card < self.current)
        tie       = next_card == self.current
        db        = self.cog.bot.db

        if tie:
            embed = discord.Embed(
                title="🃏  Higher or Lower  —  Gleichstand! 🤝",
                color=TIE_COLOR,
            )
            embed.add_field(name="Karte", value=f"Vorher: **{self.current}**  →  Jetzt: **{next_card}**", inline=False)
            embed.add_field(name="\u200b", value="Unentschieden — nochmal!", inline=False)
            embed.set_footer(text=f"💰 Einsatz: {self.einsatz:,}  •  🔥 Serie: {self.streak}")
            new_view = HiLoView(self.cog, self.user, self.einsatz, next_card, self.streak)
            self.stop()
            await interaction.response.edit_message(embed=embed, view=new_view)

        elif correct:
            self.streak += 1
            mult        = self._multiplier()
            embed = discord.Embed(
                title=f"🃏  Higher or Lower  —  Richtig! 🎉  (×{mult})",
                color=WIN_COLOR,
            )
            embed.add_field(
                name="Karten",
                value=f"Vorher: **{self.current}**  →  Jetzt: **{next_card}**",
                inline=False,
            )
            embed.add_field(
                name="🔥  Aktuelle Serie",
                value=f"**{self.streak}** richtig  →  Gewinn bei Auszahlung: **{int(self.einsatz * mult):,} Münzen**",
                inline=False,
            )
            embed.set_footer(text=f"💰 Einsatz: {self.einsatz:,}  •  Weitermachen oder Auszahlen?")
            new_view = HiLoView(self.cog, self.user, self.einsatz, next_card, self.streak)
            self.stop()
            await interaction.response.edit_message(embed=embed, view=new_view)

        else:
            await db.update_coins(self.user.id, -self.einsatz)
            await db.add_loss(self.user.id)
            xp_gain = 8 + self.streak * 2
            old_level, new_level = await db.add_xp(self.user.id, xp_gain)
            new_coins = await db.get_coins(self.user.id)
            embed = discord.Embed(
                title="🃏  Higher or Lower  —  Falsch! 💸",
                color=LOSE_COLOR,
            )
            embed.add_field(
                name="Karten",
                value=f"Vorher: **{self.current}**  →  Jetzt: **{next_card}**",
                inline=False,
            )
            embed.add_field(name="─" * 28, value=f"**-{self.einsatz:,} Münzen**", inline=False)
            embed.add_field(name="💳  Guthaben", value=f"{new_coins:,} Münzen", inline=True)
            embed.set_footer(text=f"💰 Einsatz: {self.einsatz:,}  •  Serie: {self.streak}")
            self.done = True
            for child in self.children:
                child.disabled = True
            self.play_again_btn.disabled = False
            self.stop()
            await interaction.response.edit_message(embed=embed, view=self)

            if new_level > old_level:
                from utils import level_up_embed
                await interaction.followup.send(embed=level_up_embed(self.user, old_level, new_level))

    async def cashout(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        if self.done or self.streak == 0:
            await interaction.response.send_message("Noch keine Runde gespielt!", ephemeral=True)
            return

        mult    = self._multiplier()
        payout  = int(self.einsatz * mult)
        profit  = payout - self.einsatz
        db      = self.cog.bot.db
        await db.update_coins(self.user.id, profit)
        await db.add_win(self.user.id)
        xp_gain = 8 + self.streak * 3
        old_level, new_level = await db.add_xp(self.user.id, xp_gain)
        new_coins = await db.get_coins(self.user.id)

        embed = discord.Embed(
            title=f"🃏  Higher or Lower  —  Ausgezahlt! 💰",
            color=WIN_COLOR,
        )
        embed.add_field(name="🔥  Serie",       value=f"**{self.streak}** richtig", inline=True)
        embed.add_field(name="📊  Multiplikator", value=f"×{mult}",                inline=True)
        embed.add_field(name="─" * 28,           value=f"**+{profit:,} Münzen**", inline=False)
        embed.add_field(name="💳  Guthaben",     value=f"{new_coins:,} Münzen",   inline=True)
        embed.set_thumbnail(url=self.user.display_avatar.url)
        self.done = True
        for child in self.children:
            child.disabled = True
        self.play_again_btn.disabled = False
        self.stop()
        await interaction.response.edit_message(embed=embed, view=self)

        if new_level > old_level:
            from utils import level_up_embed
            await interaction.followup.send(embed=level_up_embed(self.user, old_level, new_level))

    @discord.ui.button(label="⬆️ Höher", style=discord.ButtonStyle.success)
    async def higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.guess(interaction, higher=True)

    @discord.ui.button(label="⬇️ Niedriger", style=discord.ButtonStyle.danger)
    async def lower(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.guess(interaction, higher=False)

    @discord.ui.button(label="💰 Auszahlen", style=discord.ButtonStyle.secondary)
    async def payout(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cashout(interaction)

    @discord.ui.button(label="🔄  Nochmal spielen", style=discord.ButtonStyle.success,
                       disabled=True, row=1)
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
        first    = random.randint(1, 13)
        new_view = HiLoView(self.cog, self.user, self.einsatz, first)
        embed = discord.Embed(
            title="🃏  Higher or Lower",
            description=f"**Einsatz: {self.einsatz:,} Münzen**\nIst die nächste Karte höher oder niedriger?",
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.add_field(name="🃏  Erste Karte",    value=f"**{first}**",                  inline=True)
        embed.add_field(name="📈  Multiplikator", value="×1.0 (noch nicht gespielt)",     inline=True)
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.set_footer(text=f"🎮 {self.user.display_name}  •  Karten: 1–13")
        await interaction.response.edit_message(embed=embed, view=new_view)


# ══════════════════════════════════════════════════════════════
#  COG
# ══════════════════════════════════════════════════════════════

class MinigamesCog(commands.Cog, name="Minigames"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── %coinflip ─────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="coinflip", aliases=["cf", "münze"])
    async def coinflip(self, ctx: commands.Context, einsatz: int):
        """Münzwurf — %cf <einsatz>"""
        await self.bot.db.get_user(ctx.author.id, ctx.author.display_name)

        if einsatz < 10:
            await ctx.send("❌ Mindest-Einsatz ist **10 Münzen**!")
            return
        if einsatz > 5000:
            await ctx.send("❌ Maximal-Einsatz ist **5000 Münzen**!")
            return

        coins = await self.bot.db.get_coins(ctx.author.id)
        if coins < einsatz:
            await ctx.send(f"❌ Nicht genug Münzen! Du hast **{coins:,}** Münzen.")
            return

        embed = discord.Embed(
            title="🪙  Coinflip",
            description=f"**Einsatz: {einsatz:,} Münzen**\nWähle Kopf oder Zahl!",
            color=discord.Color.from_rgb(255, 200, 0),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"🎮 {ctx.author.display_name}  •  Gewinn: 2×")
        view = CoinflipView(self, ctx.author, einsatz)
        await ctx.send(embed=embed, view=view)

    @coinflip.error
    async def cf_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("❌ Benutzung: `%cf <einsatz>` — z.B. `%cf 100`")

    # ── %würfeln ──────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="würfeln", aliases=["dice", "würfel", "w"])
    async def wuerfeln(self, ctx: commands.Context, einsatz: int):
        """Würfelduell gegen den Bot — %würfeln <einsatz>"""
        await self.bot.db.get_user(ctx.author.id, ctx.author.display_name)

        if einsatz < 10:
            await ctx.send("❌ Mindest-Einsatz ist **10 Münzen**!")
            return
        if einsatz > 5000:
            await ctx.send("❌ Maximal-Einsatz ist **5000 Münzen**!")
            return

        coins = await self.bot.db.get_coins(ctx.author.id)
        if coins < einsatz:
            await ctx.send(f"❌ Nicht genug Münzen! Du hast **{coins:,}** Münzen.")
            return

        embed = discord.Embed(
            title="🎲  Würfelduell",
            description=(
                f"**Einsatz: {einsatz:,} Münzen**\n"
                "Beide würfeln 2 Würfel — wer mehr hat, gewinnt!\n"
                "Bei Gleichstand wird der Einsatz zurückgegeben."
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"🎮 {ctx.author.display_name}  •  Gewinn: 2×")
        view = DiceView(self, ctx.author, einsatz)
        await ctx.send(embed=embed, view=view)

    @wuerfeln.error
    async def w_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("❌ Benutzung: `%würfeln <einsatz>` — z.B. `%würfeln 100`")

    # ── %highlow ──────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="highlow", aliases=["hl", "hilo"])
    async def highlow(self, ctx: commands.Context, einsatz: int):
        """Higher or Lower — %hl <einsatz> (Streak = höherer Multiplikator!)"""
        await self.bot.db.get_user(ctx.author.id, ctx.author.display_name)

        if einsatz < 10:
            await ctx.send("❌ Mindest-Einsatz ist **10 Münzen**!")
            return
        if einsatz > 2000:
            await ctx.send("❌ Maximal-Einsatz ist **2000 Münzen**!")
            return

        coins = await self.bot.db.get_coins(ctx.author.id)
        if coins < einsatz:
            await ctx.send(f"❌ Nicht genug Münzen! Du hast **{coins:,}** Münzen.")
            return

        first = random.randint(1, 13)
        embed = discord.Embed(
            title="🃏  Higher or Lower",
            description=(
                f"**Einsatz: {einsatz:,} Münzen**\n"
                "Rate ob die nächste Karte **höher** oder **niedriger** ist!\n"
                "Jede richtige Antwort erhöht den Multiplikator (×1.5 pro Runde).\n"
                "Zahle jederzeit aus um deinen Gewinn zu sichern!"
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.add_field(name="🃏  Erste Karte", value=f"**{first}**", inline=True)
        embed.add_field(name="📈  Multiplikator", value="×1.0 (noch nicht gespielt)", inline=True)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"🎮 {ctx.author.display_name}  •  Karten: 1–13")
        view = HiLoView(self, ctx.author, einsatz, first)
        await ctx.send(embed=embed, view=view)

    @highlow.error
    async def hl_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("❌ Benutzung: `%hl <einsatz>` — z.B. `%hl 100`")


async def setup(bot: commands.Bot):
    await bot.add_cog(MinigamesCog(bot))
