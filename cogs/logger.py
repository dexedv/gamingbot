import os
import sqlite3
import discord
from discord.ext import commands

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')


def _log(
    category: str,
    action: str,
    user_id=None,
    username=None,
    target_id=None,
    target_name=None,
    details=None,
):
    """Schreibt einen Eintrag in die server_log-Tabelle (synchron)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """
            INSERT INTO server_log
                (category, action, user_id, username, target_id, target_name, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (category, action, user_id, username, target_id, target_name, details),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


class LoggerCog(commands.Cog, name="Logger"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Member ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        _log(
            category="member",
            action="Beigetreten",
            user_id=member.id,
            username=str(member),
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        _log(
            category="member",
            action="Verlassen",
            user_id=member.id,
            username=str(member),
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Rollen-Änderungen
        added_roles   = [r for r in after.roles  if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]
        for role in added_roles:
            _log(
                category="moderation",
                action="Rolle vergeben",
                user_id=after.id,
                username=str(after),
                target_id=role.id,
                target_name=role.name,
            )
        for role in removed_roles:
            _log(
                category="moderation",
                action="Rolle entzogen",
                user_id=after.id,
                username=str(after),
                target_id=role.id,
                target_name=role.name,
            )
        # Nickname-Änderung
        if before.nick != after.nick:
            _log(
                category="member",
                action="Nickname geändert",
                user_id=after.id,
                username=str(after),
                details=f"{before.nick or before.name} → {after.nick or after.name}",
            )

    # ── Moderation ────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        _log(
            category="moderation",
            action="Gebannt",
            user_id=user.id,
            username=str(user),
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        _log(
            category="moderation",
            action="Entbannt",
            user_id=user.id,
            username=str(user),
        )

    # ── Nachrichten ───────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        channel_name = getattr(message.channel, "name", str(message.channel.id))
        content = message.content or "[kein Text / Anhang]"
        _log(
            category="message",
            action="Nachricht gelöscht",
            user_id=message.author.id,
            username=str(message.author),
            target_name=f"#{channel_name}",
            details=content[:500],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot:
            return
        if before.content == after.content:
            return
        channel_name = getattr(before.channel, "name", str(before.channel.id))
        _log(
            category="message",
            action="Nachricht bearbeitet",
            user_id=before.author.id,
            username=str(before.author),
            target_name=f"#{channel_name}",
            details=f"Vorher: {before.content[:200]} | Nachher: {after.content[:200]}",
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return
        channel_name = getattr(messages[0].channel, "name", str(messages[0].channel.id))
        _log(
            category="message",
            action="Massen-Löschung",
            target_name=f"#{channel_name}",
            details=f"{len(messages)} Nachrichten gelöscht",
        )

    # ── Voice ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if before.channel is None and after.channel is not None:
            _log(
                category="voice",
                action="Voice beigetreten",
                user_id=member.id,
                username=str(member),
                target_name=after.channel.name,
            )
        elif before.channel is not None and after.channel is None:
            _log(
                category="voice",
                action="Voice verlassen",
                user_id=member.id,
                username=str(member),
                target_name=before.channel.name,
            )
        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            _log(
                category="voice",
                action="Voice gewechselt",
                user_id=member.id,
                username=str(member),
                details=f"{before.channel.name} → {after.channel.name}",
            )

    # ── Server ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        _log(
            category="server",
            action="Kanal erstellt",
            target_id=channel.id,
            target_name=channel.name,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        _log(
            category="server",
            action="Kanal gelöscht",
            target_id=channel.id,
            target_name=channel.name,
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ):
        if before.name != after.name:
            _log(
                category="server",
                action="Kanal umbenannt",
                target_id=after.id,
                target_name=after.name,
                details=f"{before.name} → {after.name}",
            )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        _log(
            category="server",
            action="Rolle erstellt",
            target_id=role.id,
            target_name=role.name,
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        _log(
            category="server",
            action="Rolle gelöscht",
            target_id=role.id,
            target_name=role.name,
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.name != after.name:
            _log(
                category="server",
                action="Rolle umbenannt",
                target_id=after.id,
                target_name=after.name,
                details=f"{before.name} → {after.name}",
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggerCog(bot))
