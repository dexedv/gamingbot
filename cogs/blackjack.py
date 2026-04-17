import discord
import random
from discord.ext import commands

SUITS  = ["♠", "♥", "♦", "♣"]
RANKS  = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
VALUES = {r: min(int(r) if r.isdigit() else 10, 10) for r in RANKS}
VALUES["A"] = 11
RED    = {"♥", "♦"}

WIN_COLOR  = discord.Color.from_rgb(87, 242, 135)
LOSE_COLOR = discord.Color.from_rgb(200, 40, 40)
PUSH_COLOR = discord.Color.from_rgb(180, 180, 180)
PLAY_COLOR = discord.Color.from_rgb(88, 101, 242)


def new_deck() -> list:
    deck = [(r, s) for s in SUITS for r in RANKS] * 6
    random.shuffle(deck)
    return deck


def hand_value(hand: list) -> int:
    val  = sum(VALUES[r] for r, _ in hand)
    aces = sum(1 for r, _ in hand if r == "A")
    while val > 21 and aces:
        val  -= 10
        aces -= 1
    return val


def card_str(rank: str, suit: str) -> str:
    return f"`{rank}{suit}`"


def hand_str(hand: list, hide_second: bool = False) -> str:
    if hide_second and len(hand) >= 2:
        return f"{card_str(*hand[0])}  `??`"
    return "  ".join(card_str(*c) for c in hand)


class BlackjackView(discord.ui.View):
    def __init__(self, cog, user: discord.Member, einsatz: int,
                 deck: list, player: list, dealer: list, doubled: bool = False):
        super().__init__(timeout=120)
        self.cog    = cog
        self.user   = user
        self.einsatz = einsatz
        self.deck   = deck
        self.player = player
        self.dealer = dealer
        self.doubled = doubled
        self.done   = False

        # Double nur bei erster Runde anzeigen
        if len(player) != 2:
            self.double_btn.disabled = True

    def build_embed(self, *, reveal: bool = False, title: str = "🃏  Blackjack",
                    color: discord.Color = PLAY_COLOR, extra: str = "") -> discord.Embed:
        pval = hand_value(self.player)
        dval = hand_value(self.dealer)

        embed = discord.Embed(title=title, color=color)
        embed.add_field(
            name=f"🙋  Deine Hand  —  **{pval}**",
            value=hand_str(self.player),
            inline=False,
        )
        if reveal:
            embed.add_field(
                name=f"🤖  Dealer  —  **{dval}**",
                value=hand_str(self.dealer),
                inline=False,
            )
        else:
            embed.add_field(
                name="🤖  Dealer  —  **?**",
                value=hand_str(self.dealer, hide_second=True),
                inline=False,
            )
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        embed.set_footer(text=f"💰 Einsatz: {self.einsatz:,} Münzen  •  🎮 {self.user.display_name}")
        embed.set_thumbnail(url=self.user.display_avatar.url)
        return embed

    async def finish(self, interaction: discord.Interaction):
        """Dealer spielt aus und Ergebnis wird ermittelt."""
        for child in self.children:
            child.disabled = True

        # Dealer zieht bis >= 17
        while hand_value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())

        pval = hand_value(self.player)
        dval = hand_value(self.dealer)
        db   = self.cog.bot.db

        if dval > 21 or pval > dval:
            title  = "🃏  Blackjack  —  Du gewinnst! 🎉"
            profit = self.einsatz
            extra  = f"**+{profit:,} Münzen**"
            color  = WIN_COLOR
            await db.update_coins(self.user.id, profit)
            await db.add_win(self.user.id)
            xp_gain = 25
        elif pval < dval:
            title  = "🃏  Blackjack  —  Dealer gewinnt 💸"
            extra  = f"**-{self.einsatz:,} Münzen**"
            color  = LOSE_COLOR
            await db.add_loss(self.user.id)
            xp_gain = 15
        else:
            title  = "🃏  Blackjack  —  Unentschieden 🤝"
            extra  = "Einsatz zurück — **±0 Münzen**"
            color  = PUSH_COLOR
            await db.update_coins(self.user.id, self.einsatz)
            await db.add_draw(self.user.id)
            xp_gain = 15

        old_level, new_level = await db.add_xp(self.user.id, xp_gain)
        new_coins = await db.get_coins(self.user.id)
        embed = self.build_embed(reveal=True, title=title, color=color,
                                 extra=f"{extra}\n💳 Guthaben: **{new_coins:,} Münzen**")
        self.done = True
        self.play_again_btn.disabled = False
        self.stop()
        await interaction.response.edit_message(embed=embed, view=self)

        if new_level > old_level:
            from utils import level_up_embed, send_notify
            await send_notify(self.cog.bot, level_up_embed(self.user, old_level, new_level))

    # ── Buttons ───────────────────────────────────────────────────────────────

    @discord.ui.button(label="Hit 🃏", style=discord.ButtonStyle.primary)
    async def hit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        if self.done:
            return

        self.player.append(self.deck.pop())
        self.double_btn.disabled = True  # kein Double nach Hit
        pval = hand_value(self.player)

        if pval > 21:
            # Bust
            for child in self.children:
                child.disabled = True
            db = self.cog.bot.db
            await db.add_loss(self.user.id)
            old_level, new_level = await db.add_xp(self.user.id, 15)
            new_coins = await db.get_coins(self.user.id)
            embed = self.build_embed(
                reveal=True,
                title="🃏  Blackjack  —  Bust! 💥",
                color=LOSE_COLOR,
                extra=f"**-{self.einsatz:,} Münzen**\n💳 Guthaben: **{new_coins:,} Münzen**",
            )
            self.done = True
            self.play_again_btn.disabled = False
            self.stop()
            await interaction.response.edit_message(embed=embed, view=self)
            if new_level > old_level:
                from utils import level_up_embed
                await interaction.followup.send(embed=level_up_embed(self.user, old_level, new_level))
        elif pval == 21:
            await self.finish(interaction)
        else:
            embed = self.build_embed(
                title=f"🃏  Blackjack  —  Du hast **{pval}**",
                color=PLAY_COLOR,
            )
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand ✋", style=discord.ButtonStyle.secondary)
    async def stand_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        if self.done:
            return
        await self.finish(interaction)

    @discord.ui.button(label="Double ⬆️", style=discord.ButtonStyle.danger)
    async def double_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        if self.done:
            return

        db    = self.cog.bot.db
        coins = await db.get_coins(self.user.id)
        if coins < self.einsatz:
            await interaction.response.send_message(
                f"❌ Nicht genug Münzen für Double Down! (brauchst **{self.einsatz:,}**)", ephemeral=True
            )
            return

        await db.update_coins(self.user.id, -self.einsatz)
        self.einsatz *= 2
        self.player.append(self.deck.pop())
        button.disabled = True

        pval = hand_value(self.player)
        if pval > 21:
            for child in self.children:
                child.disabled = True
            await db.add_loss(self.user.id)
            old_level, new_level = await db.add_xp(self.user.id, 15)
            new_coins = await db.get_coins(self.user.id)
            embed = self.build_embed(
                reveal=True,
                title="🃏  Blackjack  —  Bust nach Double! 💥",
                color=LOSE_COLOR,
                extra=f"**-{self.einsatz:,} Münzen**\n💳 Guthaben: **{new_coins:,} Münzen**",
            )
            self.done = True
            self.play_again_btn.disabled = False
            self.stop()
            await interaction.response.edit_message(embed=embed, view=self)
            if new_level > old_level:
                from utils import level_up_embed
                await interaction.followup.send(embed=level_up_embed(self.user, old_level, new_level))
        else:
            await self.finish(interaction)

    @discord.ui.button(label="🔄  Nochmal spielen", style=discord.ButtonStyle.success,
                       disabled=True, row=1)
    async def play_again_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Nicht dein Spiel!", ephemeral=True)
            return
        db    = self.cog.bot.db
        coins = await db.get_coins(self.user.id)
        orig  = self.einsatz // 2 if hasattr(self, '_doubled') else self.einsatz
        bet   = min(self.einsatz, orig)  # Ursprünglichen Einsatz wiederverwenden
        if coins < bet:
            await interaction.response.send_message(
                f"❌ Nicht genug Münzen! Du hast **{coins:,}** Münzen.", ephemeral=True
            )
            return
        button.disabled = True
        await db.update_coins(self.user.id, -bet)
        deck   = new_deck()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]
        new_view = BlackjackView(self.cog, self.user, bet, deck, player, dealer)
        embed = new_view.build_embed(
            title=f"🃏  Blackjack  —  Du hast **{hand_value(player)}**",
            color=PLAY_COLOR,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class BlackjackCog(commands.Cog, name="Blackjack"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="blackjack", aliases=["bj"])
    async def blackjack(self, ctx: commands.Context, einsatz: int):
        """Spiele Blackjack gegen den Dealer — %bj <einsatz>"""
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

        await self.bot.db.update_coins(ctx.author.id, -einsatz)

        deck   = new_deck()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        # Blackjack sofort prüfen
        if hand_value(player) == 21:
            payout = int(einsatz * 2.5)  # 1.5x Gewinn
            profit = payout - einsatz
            await self.bot.db.update_coins(ctx.author.id, payout)
            await self.bot.db.add_win(ctx.author.id)
            new_coins = await self.bot.db.get_coins(ctx.author.id)

            embed = discord.Embed(title="🃏  BLACKJACK! 🌟", color=WIN_COLOR)
            embed.add_field(name="🙋  Deine Hand  —  **21**", value=hand_str(player), inline=False)
            embed.add_field(name="🤖  Dealer", value=hand_str(dealer), inline=False)
            embed.add_field(name="\u200b",
                            value=f"**+{profit:,} Münzen** (1.5×)\n💳 Guthaben: **{new_coins:,} Münzen**",
                            inline=False)
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            embed.set_footer(text=f"💰 Einsatz: {einsatz:,} Münzen  •  🎮 {ctx.author.display_name}")
            await ctx.send(embed=embed)
            return

        view  = BlackjackView(self, ctx.author, einsatz, deck, player, dealer)
        embed = view.build_embed(
            title=f"🃏  Blackjack  —  Du hast **{hand_value(player)}**",
            color=PLAY_COLOR,
        )
        await ctx.send(embed=embed, view=view)

    @blackjack.error
    async def bj_error(self, ctx, error):
        if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send("❌ Benutzung: `%bj <einsatz>` — z.B. `%bj 200`")


async def setup(bot: commands.Bot):
    await bot.add_cog(BlackjackCog(bot))
