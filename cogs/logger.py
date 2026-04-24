import os
import re
import sqlite3
import discord
from discord.ext import commands

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')

# Nickname-Muster das der Bot setzt: "Name | 5🔥"
_STREAK_NICK_RE = re.compile(r'\| \d+🔥$')


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


async def _actor_is_bot(guild: discord.Guild, action: discord.AuditLogAction, target_id: int | None = None) -> bool:
    """Gibt True zurück wenn der letzte Audit-Log-Eintrag dieser Aktion vom Bot stammt."""
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            if target_id is not None:
                if not (hasattr(entry.target, "id") and entry.target.id == target_id):
                    continue
            return entry.user is not None and entry.user.bot
    except Exception:
        pass
    return False


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
        # ── Rollen-Änderungen ──────────────────────────────────────────────
        added_roles   = [r for r in after.roles  if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]
        if added_roles or removed_roles:
            # Nur loggen wenn ein Mensch (kein Bot) die Änderung gemacht hat
            if not await _actor_is_bot(after.guild, discord.AuditLogAction.member_role_update, after.id):
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

        # ── Nickname-Änderung ──────────────────────────────────────────────
        if before.nick != after.nick:
            # Bot-Streak-Nicknames überspringen (Format: "Name | 5🔥")
            if after.nick and _STREAK_NICK_RE.search(after.nick):
                return
            if before.nick and _STREAK_NICK_RE.search(before.nick) and not after.nick:
                return  # Bot-Nick wurde entfernt (z.B. bei Neustart)
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
        if member.bot:
            return
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
        if await _actor_is_bot(channel.guild, discord.AuditLogAction.channel_create):
            return
        _log(
            category="server",
            action="Kanal erstellt",
            target_id=channel.id,
            target_name=channel.name,
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if await _actor_is_bot(channel.guild, discord.AuditLogAction.channel_delete):
            return
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
            if await _actor_is_bot(after.guild, discord.AuditLogAction.channel_update):
                return
            _log(
                category="server",
                action="Kanal umbenannt",
                target_id=after.id,
                target_name=after.name,
                details=f"{before.name} → {after.name}",
            )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        if await _actor_is_bot(role.guild, discord.AuditLogAction.role_create):
            return
        _log(
            category="server",
            action="Rolle erstellt",
            target_id=role.id,
            target_name=role.name,
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        if await _actor_is_bot(role.guild, discord.AuditLogAction.role_delete):
            return
        _log(
            category="server",
            action="Rolle gelöscht",
            target_id=role.id,
            target_name=role.name,
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.name != after.name:
            if await _actor_is_bot(after.guild, discord.AuditLogAction.role_update):
                return
            _log(
                category="server",
                action="Rolle umbenannt",
                target_id=after.id,
                target_name=after.name,
                details=f"{before.name} → {after.name}",
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggerCog(bot))
