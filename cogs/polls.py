import discord
from discord.ext import commands


OPTION_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
OPTION_STYLES = [
    discord.ButtonStyle.primary,
    discord.ButtonStyle.success,
    discord.ButtonStyle.danger,
    discord.ButtonStyle.secondary,
    discord.ButtonStyle.primary,
]


class PollButton(discord.ui.Button):
    def __init__(self, index: int, label: str):
        super().__init__(
            style=OPTION_STYLES[index],
            label=f"{OPTION_EMOJIS[index]} {label}"[:80],
            custom_id=f"poll_opt_{index}",
            row=index // 3,
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: PollView = self.view
        user_id = interaction.user.id
        prev = view.votes.get(user_id)

        if prev == self.index:
            del view.votes[user_id]
            feedback = f"✅ Stimme für **{self.label}** entfernt."
        else:
            view.votes[user_id] = self.index
            feedback = f"✅ Du hast für **{self.label}** gestimmt."

        await interaction.response.edit_message(embed=view.build_embed())
        await interaction.followup.send(feedback, ephemeral=True)


class PollView(discord.ui.View):
    def __init__(self, question: str, options: list[str], author: discord.Member):
        super().__init__(timeout=None)
        self.question = question
        self.options = options
        self.votes: dict[int, int] = {}
        self.author = author
        self.closed = False

        for i, opt in enumerate(options):
            self.add_item(PollButton(i, opt))

    def build_embed(self, final: bool = False) -> discord.Embed:
        total = len(self.votes)
        counts = [0] * len(self.options)
        for idx in self.votes.values():
            counts[idx] += 1

        lines = []
        for i, (opt, cnt) in enumerate(zip(self.options, counts)):
            filled = int(cnt / total * 10) if total > 0 else 0
            bar = "█" * filled + "░" * (10 - filled)
            pct = f"{cnt / total * 100:.0f}%" if total > 0 else "0%"
            lines.append(
                f"{OPTION_EMOJIS[i]} **{opt}**\n`{bar}` {cnt} Stimme{'n' if cnt != 1 else ''} ({pct})"
            )

        closed = self.closed or final
        embed = discord.Embed(
            title=f"{'🔒 ' if closed else '📊 '}{'[Abgeschlossen] ' if closed else ''}{self.question}",
            description="\n\n".join(lines),
            color=discord.Color.greyple() if closed else discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"{'Abgeschlossen' if closed else 'Aktiv'} · {total} Stimme{'n' if total != 1 else ''} · "
                 f"Von {self.author.display_name} · Klicke erneut zum Entfernen"
        )
        return embed


class PollsCog(commands.Cog, name="Polls"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._polls: dict[int, PollView] = {}

    @commands.command(name="umfrage", aliases=["poll"])
    async def poll_cmd(self, ctx: commands.Context, frage: str, *optionen: str):
        """Erstellt eine Umfrage — %umfrage "Frage" option1 option2 [option3 ...]"""
        opts = list(optionen[:5])
        if len(opts) < 2:
            await ctx.send(
                '❌ Mindestens 2 Optionen angeben.\n'
                'Beispiel: `%umfrage "Lieblingsfarbe?" Blau Rot Grün`'
            )
            return

        view = PollView(frage, opts, ctx.author)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        self._polls[msg.id] = view

    @commands.command(name="umfrage-ende", aliases=["pollende", "poll-end"])
    async def poll_end_cmd(self, ctx: commands.Context, message_id: str):
        """Schließt eine Umfrage — %umfrage-ende <message_id>"""
        try:
            mid = int(message_id)
        except ValueError:
            await ctx.send("❌ Ungültige Nachrichten-ID.")
            return

        view = self._polls.get(mid)
        if not view:
            await ctx.send("❌ Umfrage nicht gefunden oder bereits abgeschlossen.")
            return

        if ctx.author != view.author and not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ Du kannst nur deine eigenen Umfragen schließen.")
            return

        view.closed = True
        view.stop()
        try:
            msg = await ctx.channel.fetch_message(mid)
            await msg.edit(embed=view.build_embed(final=True), view=None)
        except Exception:
            pass
        del self._polls[mid]
        await ctx.send("🔒 Umfrage wurde abgeschlossen.")


async def setup(bot: commands.Bot):
    await bot.add_cog(PollsCog(bot))
