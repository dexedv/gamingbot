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
    def __init__(self, question: str, options: list[str],
                 author_name: str = "Dashboard", channel_id: int = 0):
        super().__init__(timeout=None)
        self.question = question
        self.options = options
        self.votes: dict[int, int] = {}
        self.author_name = author_name
        self.channel_id = channel_id
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
            text=f"{'Abgeschlossen' if closed else 'Aktiv'} · "
                 f"{total} Stimme{'n' if total != 1 else ''} · "
                 f"Von {self.author_name} · Klicke erneut zum Entfernen"
        )
        return embed

    def to_dict(self, message_id: int) -> dict:
        total = len(self.votes)
        counts = [0] * len(self.options)
        for idx in self.votes.values():
            counts[idx] += 1
        return {
            "message_id":  str(message_id),
            "question":    self.question,
            "author":      self.author_name,
            "channel_id":  str(self.channel_id),
            "total_votes": total,
            "options": [
                {"text": opt, "count": cnt,
                 "pct": round(cnt / total * 100) if total else 0}
                for opt, cnt in zip(self.options, counts)
            ],
        }


class PollsCog(commands.Cog, name="Polls"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._polls: dict[int, PollView] = {}

    # ── Discord-Befehle ───────────────────────────────────────────────────────

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

        view = PollView(frage, opts,
                        author_name=ctx.author.display_name,
                        channel_id=ctx.channel.id)
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

        if not ctx.author.guild_permissions.manage_messages and view.author_name != ctx.author.display_name:
            await ctx.send("❌ Du kannst nur deine eigenen Umfragen schließen.")
            return

        await self._close_poll(mid, view)
        await ctx.send("🔒 Umfrage wurde abgeschlossen.")

    # ── Hilfsmethoden (auch für Dashboard) ───────────────────────────────────

    async def create_poll(self, channel_id: int, question: str,
                          options: list[str], author_name: str = "Dashboard") -> dict:
        """Erstellt und sendet eine Umfrage in den angegebenen Kanal."""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            raise ValueError("Kanal nicht gefunden")
        view = PollView(question, options,
                        author_name=author_name,
                        channel_id=channel_id)
        msg = await channel.send(embed=view.build_embed(), view=view)
        self._polls[msg.id] = view
        return {"message_id": str(msg.id), "channel": channel.name}

    async def close_poll(self, message_id: int) -> dict:
        """Schließt eine aktive Umfrage."""
        view = self._polls.get(message_id)
        if not view:
            raise ValueError("Umfrage nicht gefunden")
        result = view.to_dict(message_id)
        await self._close_poll(message_id, view)
        return result

    async def _close_poll(self, message_id: int, view: PollView):
        view.closed = True
        view.stop()
        channel = self.bot.get_channel(view.channel_id)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.edit(embed=view.build_embed(final=True), view=None)
            except Exception:
                pass
        self._polls.pop(message_id, None)

    def list_polls(self) -> list[dict]:
        return [v.to_dict(mid) for mid, v in self._polls.items()]


async def setup(bot: commands.Bot):
    await bot.add_cog(PollsCog(bot))
