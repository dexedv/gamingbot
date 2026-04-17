import discord
from discord.ext import commands

X_MARK = "❌"
O_MARK = "⭕"
WIN_COINS = 200
LOSS_COINS = 100


class TicTacToeButton(discord.ui.Button):
    def __init__(self, x: int, y: int):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="\u200b",
            row=y,
        )
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view: TicTacToeView = self.view  # type: ignore

        if interaction.user.id != view.current_player.id:
            await interaction.response.send_message("Du bist nicht dran!", ephemeral=True)
            return

        if view.board[self.y][self.x] != 0:
            await interaction.response.send_message("Dieses Feld ist schon belegt!", ephemeral=True)
            return

        if view.current_player.id == view.player_x.id:
            view.board[self.y][self.x] = 1
            self.label = X_MARK
            self.style = discord.ButtonStyle.danger
        else:
            view.board[self.y][self.x] = 2
            self.label = O_MARK
            self.style = discord.ButtonStyle.primary

        self.disabled = True
        db = view.cog.bot.db
        winner = view.check_winner()

        if winner:
            for child in view.children:
                child.disabled = True  # type: ignore

            win_player = view.player_x if winner == 1 else view.player_o
            lose_player = view.player_o if winner == 1 else view.player_x

            await db.update_coins(win_player.id, WIN_COINS)
            await db.update_coins(lose_player.id, -LOSS_COINS)
            await db.add_win(win_player.id)
            await db.add_loss(lose_player.id)
            win_old_lv, win_new_lv   = await db.add_xp(win_player.id, 25)
            lose_old_lv, lose_new_lv = await db.add_xp(lose_player.id, 10)

            win_bal  = await db.get_coins(win_player.id)
            lose_bal = await db.get_coins(lose_player.id)

            embed = view.build_embed(
                title=f"🏆 {win_player.display_name} hat gewonnen!",
                color=discord.Color.green(),
                extra=(
                    f"💰 **+{WIN_COINS}** Münzen → {win_player.display_name} ({win_bal:,})\n"
                    f"💸 **-{LOSS_COINS}** Münzen → {lose_player.display_name} ({lose_bal:,})"
                ),
            )
            view.stop()
            await interaction.response.edit_message(content=None, embed=embed, view=view)

            from utils import level_up_embed, send_notify
            if win_new_lv > win_old_lv:
                await send_notify(self.cog.bot, level_up_embed(win_player, win_old_lv, win_new_lv))
            if lose_new_lv > lose_old_lv:
                await send_notify(self.cog.bot, level_up_embed(lose_player, lose_old_lv, lose_new_lv))

        elif view.is_board_full():
            for child in view.children:
                child.disabled = True  # type: ignore

            await db.add_draw(view.player_x.id)
            await db.add_draw(view.player_o.id)
            x_old_lv, x_new_lv = await db.add_xp(view.player_x.id, 15)
            o_old_lv, o_new_lv = await db.add_xp(view.player_o.id, 15)

            embed = view.build_embed(
                title="🤝 Unentschieden!",
                color=discord.Color.greyple(),
                extra="Keine Münzen gewonnen oder verloren.",
            )
            view.stop()
            await interaction.response.edit_message(content=None, embed=embed, view=view)

            from utils import level_up_embed, send_notify
            if x_new_lv > x_old_lv:
                await send_notify(self.cog.bot, level_up_embed(view.player_x, x_old_lv, x_new_lv))
            if o_new_lv > o_old_lv:
                await send_notify(self.cog.bot, level_up_embed(view.player_o, o_old_lv, o_new_lv))

        else:
            view.current_player = (
                view.player_o if view.current_player.id == view.player_x.id else view.player_x
            )
            embed = view.build_embed(
                title="Tic-Tac-Toe",
                color=discord.Color.blurple(),
                extra=f"🎮 Am Zug: **{view.current_player.display_name}**",
            )
            await interaction.response.edit_message(content=None, embed=embed, view=view)


class TicTacToeView(discord.ui.View):
    def __init__(self, cog, player_x: discord.Member, player_o: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.player_x = player_x
        self.player_o = player_o
        self.current_player = player_x
        self.board: list[list[int]] = [[0] * 3 for _ in range(3)]

        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_winner(self) -> int | None:
        b = self.board
        for row in b:
            if row[0] == row[1] == row[2] != 0:
                return row[0]
        for col in range(3):
            if b[0][col] == b[1][col] == b[2][col] != 0:
                return b[0][col]
        if b[0][0] == b[1][1] == b[2][2] != 0:
            return b[0][0]
        if b[0][2] == b[1][1] == b[2][0] != 0:
            return b[0][2]
        return None

    def is_board_full(self) -> bool:
        return all(self.board[y][x] != 0 for y in range(3) for x in range(3))

    def build_embed(self, *, title: str, color: discord.Color, extra: str) -> discord.Embed:
        embed = discord.Embed(title=title, color=color)
        embed.description = (
            f"{X_MARK}  **{self.player_x.display_name}**"
            f"  `VS`  "
            f"**{self.player_o.display_name}**  {O_MARK}\n"
            f"─────────────────────────\n"
            f"{extra}"
        )
        embed.set_footer(text=f"🏆 Gewinner: +{WIN_COINS}  •  💸 Verlierer: -{LOSS_COINS} Münzen")
        return embed

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True  # type: ignore


class AcceptView(discord.ui.View):
    def __init__(self, cog, challenger: discord.Member, opponent: discord.Member):
        super().__init__(timeout=60)
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent

    @discord.ui.button(label="Annehmen ✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Diese Anfrage ist nicht für dich!", ephemeral=True)
            return

        self.stop()
        game_view = TicTacToeView(self.cog, self.challenger, self.opponent)
        embed = game_view.build_embed(
            title="Tic-Tac-Toe",
            color=discord.Color.blurple(),
            extra=f"🎮 Am Zug: **{self.challenger.display_name}**",
        )
        await interaction.response.edit_message(content=None, embed=embed, view=game_view)

    @discord.ui.button(label="Ablehnen ❌", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.opponent.id, self.challenger.id):
            await interaction.response.send_message("Das geht dich nichts an!", ephemeral=True)
            return

        self.stop()
        await interaction.response.edit_message(
            content=f"❌ **{self.opponent.display_name}** hat die Herausforderung abgelehnt.",
            view=None,
        )


class TicTacToeCog(commands.Cog, name="TicTacToe"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="tictactoe", aliases=["ttt"])
    async def tictactoe(self, ctx: commands.Context, gegner: discord.Member):
        """Fordere jemanden zu Tic-Tac-Toe heraus"""
        if gegner.id == ctx.author.id:
            await ctx.send("Du kannst nicht gegen dich selbst spielen!")
            return
        if gegner.bot:
            await ctx.send("Du kannst nicht gegen einen Bot spielen!")
            return

        await self.bot.db.get_user(ctx.author.id, ctx.author.display_name)
        await self.bot.db.get_user(gegner.id, gegner.display_name)

        view = AcceptView(self, ctx.author, gegner)
        await ctx.send(
            f"🎮 **{ctx.author.display_name}** fordert **{gegner.mention}** zu Tic-Tac-Toe heraus!\n"
            f"Gewinner: **+{WIN_COINS} Münzen** | Verlierer: **-{LOSS_COINS} Münzen**",
            view=view,
        )

    @tictactoe.error
    async def tictactoe_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Benutzung: `%tictactoe @spieler`")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Spieler nicht gefunden! Erwähne einen Server-Mitglied mit @.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TicTacToeCog(bot))
