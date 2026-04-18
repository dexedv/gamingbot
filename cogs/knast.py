import discord
import json
import sqlite3
import os
from discord.ext import commands

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')

KNAST_ALLOWED_ROLES = {
    1019393672825028639,
    1019392564924788756,
    1494057242197229598,
    1494042802659524829,
}


def has_knast_permission():
    """Check: Nutzer muss eine der erlaubten Knast-Rollen haben."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author == ctx.guild.owner:
            return True
        user_role_ids = {r.id for r in ctx.author.roles}
        if user_role_ids & KNAST_ALLOWED_ROLES:
            return True
        raise commands.CheckFailure("Du hast keine Berechtigung für den Knast-Befehl.")
    return commands.check(predicate)


def _load_knast_settings() -> dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT key, value FROM bot_settings WHERE key LIKE 'knast_%'"
        ).fetchall()
        conn.close()
        result = {}
        for key, val in rows:
            try:
                result[key] = json.loads(val)
            except Exception:
                result[key] = val
        return result
    except Exception:
        return {}


def _save_knast_settings(data: dict):
    conn = sqlite3.connect(DB_PATH)
    for key, val in data.items():
        conn.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(val))
        )
    conn.commit()
    conn.close()


class KnastCog(commands.Cog, name="Knast"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Hilfsfunktionen ───────────────────────────────────────────────────────

    def _is_jailed(self, user_id: int) -> bool:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT 1 FROM knast WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        return row is not None

    async def _apply_jail(self, member: discord.Member, jail_category: discord.CategoryChannel):
        """Setzt user-spezifische Channel-Overrides für alle Kanäle."""
        for channel in member.guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
            if channel.category_id == jail_category.id:
                await channel.set_permissions(member, view_channel=True)
            else:
                await channel.set_permissions(member, view_channel=False)

    async def _remove_jail_overrides(self, member: discord.Member):
        """Entfernt alle user-spezifischen Overrides wieder."""
        for channel in member.guild.channels:
            if isinstance(channel, discord.CategoryChannel):
                continue
            overwrite = channel.overwrites_for(member)
            if overwrite.view_channel is not None:
                await channel.set_permissions(member, overwrite=None)

    # ── Befehle ───────────────────────────────────────────────────────────────

    @commands.group(name="knast", invoke_without_command=True)
    @has_knast_permission()
    async def knast_cmd(self, ctx: commands.Context):
        """Knast-System — Sperrt Nutzer in eine isolierte Zelle."""
        embed = discord.Embed(
            title="🔒 Knast-System",
            description=(
                "`%knast setup` — Erstellt Knast-Infrastruktur\n"
                "`%knast add @nutzer [Grund]` — Nutzer einsperren\n"
                "`%knast remove @nutzer [Grund]` — Nutzer entlassen\n"
                "`%knast list` — Alle Insassen anzeigen"
            ),
            color=discord.Color.from_rgb(128, 0, 0),
        )
        await ctx.send(embed=embed)

    @knast_cmd.command(name="setup")
    @has_knast_permission()
    async def knast_setup(self, ctx: commands.Context, category_id: int = None):
        """Richtet das Knast-System ein. Optionale Kategorie-ID für eine bestehende Kategorie.
        Beispiel: %knast setup 1494945960957050941"""
        guild = ctx.guild
        msg = await ctx.send("⏳ Richte Knast-System ein…")

        # Rolle anlegen
        jail_role = discord.utils.get(guild.roles, name="Knast")
        if not jail_role:
            jail_role = await guild.create_role(
                name="Knast",
                color=discord.Color.from_rgb(100, 0, 0),
                reason="Knast-System Setup",
            )

        # Kategorie — entweder per ID oder neu erstellen
        if category_id:
            jail_cat = guild.get_channel(category_id)
            if not jail_cat or not isinstance(jail_cat, discord.CategoryChannel):
                await msg.edit(content=f"❌ Keine Kategorie mit ID `{category_id}` gefunden.")
                return
        else:
            jail_cat = discord.utils.get(guild.categories, name="Gefängnis")

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            jail_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                speak=False,
                connect=True,
            ),
        }

        if not jail_cat:
            jail_cat = await guild.create_category("Gefängnis", overwrites=overwrites)
        else:
            await jail_cat.edit(overwrites=overwrites)

        # Text-Kanal (ersten bestehenden nehmen oder neu erstellen)
        text_ch = jail_cat.text_channels[0] if jail_cat.text_channels else None
        if not text_ch:
            text_ch = await guild.create_text_channel(
                "gefaengnis-zelle",
                category=jail_cat,
                topic="Du bist im Knast. Warte auf einen Moderator.",
            )

        # Voice-Kanal (ersten bestehenden nehmen oder neu erstellen)
        voice_ch = jail_cat.voice_channels[0] if jail_cat.voice_channels else None
        if not voice_ch:
            voice_ch = await guild.create_voice_channel(
                "🔒 Gefängnis",
                category=jail_cat,
            )

        # Einstellungen speichern
        _save_knast_settings({
            "knast_category":      jail_cat.id,
            "knast_text_channel":  text_ch.id,
            "knast_voice_channel": voice_ch.id,
            "knast_role":          jail_role.id,
        })

        embed = discord.Embed(
            title="✅ Knast-System eingerichtet",
            color=discord.Color.from_rgb(34, 197, 94),
        )
        embed.add_field(name="📂 Kategorie",  value=f"{jail_cat.name} (`{jail_cat.id}`)", inline=False)
        embed.add_field(name="💬 Text",       value=f"#{text_ch.name}", inline=True)
        embed.add_field(name="🔊 Voice",      value=voice_ch.name,      inline=True)
        embed.add_field(name="🎭 Rolle",      value=f"@{jail_role.name}", inline=True)
        embed.set_footer(text="Nutze %knast add @nutzer um jemanden einzusperren")
        await msg.edit(content="", embed=embed)

    @knast_cmd.command(name="add")
    @has_knast_permission()
    async def knast_add(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Kein Grund angegeben"):
        """Sperrt einen Nutzer in den Knast. — %knast add @nutzer [Grund]"""
        if member.bot:
            await ctx.send("❌ Bots können nicht eingesperrt werden.")
            return
        if member == ctx.author:
            await ctx.send("❌ Du kannst dich nicht selbst einsperren.")
            return
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("❌ Du kannst diesen Nutzer nicht einsperren (gleiche oder höhere Rolle).")
            return
        if self._is_jailed(member.id):
            await ctx.send(f"⚠️ {member.mention} ist bereits im Knast.")
            return

        settings = _load_knast_settings()
        if not settings.get("knast_category"):
            await ctx.send("❌ Knast nicht eingerichtet. Nutze zuerst `%knast setup`.")
            return

        jail_cat    = ctx.guild.get_channel(int(settings["knast_category"]))
        jail_role   = ctx.guild.get_role(int(settings["knast_role"]))
        jail_text   = ctx.guild.get_channel(int(settings["knast_text_channel"]))
        jail_voice  = ctx.guild.get_channel(int(settings["knast_voice_channel"]))

        if not jail_cat or not jail_role:
            await ctx.send("❌ Knast-Konfiguration ungültig. Bitte `%knast setup` erneut ausführen.")
            return

        msg = await ctx.send(f"⏳ Sperre **{member.display_name}** ein…")

        # Rollen sichern (ohne @everyone und nicht entfernbare)
        removable = [r for r in member.roles if r != ctx.guild.default_role and not r.managed]
        role_ids  = [r.id for r in removable]

        # DB-Eintrag (aktiver Knast + permanenter Log)
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO knast (user_id, guild_id, roles, reason, jailed_by) VALUES (?, ?, ?, ?, ?)",
            (member.id, ctx.guild.id, json.dumps(role_ids), reason, str(ctx.author.id))
        )
        conn.execute(
            "INSERT INTO knast_log (action, user_id, username, by_id, by_name, reason) VALUES (?, ?, ?, ?, ?, ?)",
            ("jail", member.id, str(member), ctx.author.id, str(ctx.author), reason)
        )
        conn.commit()
        conn.close()

        # Rollen entfernen → Knast-Rolle geben
        try:
            if removable:
                await member.remove_roles(*removable, reason=f"Knast: {reason}")
            await member.add_roles(jail_role, reason=f"Knast: {reason}")
        except discord.Forbidden:
            await msg.edit(content="❌ Fehlende Berechtigung zum Verwalten von Rollen.")
            return

        # Kanal-Overrides setzen
        await self._apply_jail(member, jail_cat)

        # Falls im Voice → in Knast-Voice verschieben oder kicken
        if member.voice and member.voice.channel:
            if member.voice.channel.category_id != jail_cat.id:
                try:
                    if jail_voice:
                        await member.move_to(jail_voice, reason="Knast")
                    else:
                        await member.move_to(None, reason="Knast")
                except discord.Forbidden:
                    pass

        # Nachricht in Knast-Kanal
        if jail_text:
            embed = discord.Embed(
                title="🔒 Du wurdest eingesperrt",
                description=(
                    f"Hey {member.mention}, du hast gegen die Regeln verstoßen und wurdest in den Knast gesperrt.\n\n"
                    f"**Grund:** {reason}\n\n"
                    f"Du kannst nur noch diesen Kanal sehen. Bitte warte auf einen Moderator."
                ),
                color=discord.Color.from_rgb(128, 0, 0),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Eingesperrt von {ctx.author.display_name}")
            await jail_text.send(member.mention, embed=embed)

        # Log
        from utils import send_log
        await send_log(
            self.bot,
            "🔒 Nutzer eingesperrt",
            f"👤  **Nutzer:** {member} (`{member.id}`)\n"
            f"👮  **Von:** {ctx.author}\n"
            f"📝  **Grund:** {reason}\n"
            f"🎭  **Gesicherte Rollen:** {len(role_ids)}",
            discord.Color.from_rgb(128, 0, 0),
        )

        await msg.edit(content=f"🔒 **{member.display_name}** wurde eingesperrt! Grund: *{reason}*")

    @knast_cmd.command(name="remove", aliases=["free", "raus", "entlassen"])
    @has_knast_permission()
    async def knast_remove(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Kein Grund angegeben"):
        """Entlässt einen Nutzer aus dem Knast. — %knast remove @nutzer [Grund]"""
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT roles FROM knast WHERE user_id = ?", (member.id,)).fetchone()
        conn.close()

        if not row:
            await ctx.send(f"⚠️ {member.mention} ist nicht im Knast.")
            return

        role_ids = json.loads(row[0])
        settings = _load_knast_settings()
        msg = await ctx.send(f"⏳ Entlasse **{member.display_name}**…")

        # Knast-Rolle entfernen
        jail_role_id = settings.get("knast_role")
        if jail_role_id:
            jail_role = ctx.guild.get_role(int(jail_role_id))
            if jail_role:
                try:
                    await member.remove_roles(jail_role, reason=f"Knast-Entlassung: {reason}")
                except discord.Forbidden:
                    pass

        # Kanal-Overrides entfernen
        await self._remove_jail_overrides(member)

        # Alte Rollen wiederherstellen
        roles_to_restore = []
        for role_id in role_ids:
            role = ctx.guild.get_role(role_id)
            if role and not role.managed:
                roles_to_restore.append(role)
        if roles_to_restore:
            try:
                await member.add_roles(*roles_to_restore, reason="Knast-Entlassung")
            except discord.Forbidden:
                pass

        # DB-Eintrag löschen + permanenter Log
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM knast WHERE user_id = ?", (member.id,))
        conn.execute(
            "INSERT INTO knast_log (action, user_id, username, by_id, by_name, reason) VALUES (?, ?, ?, ?, ?, ?)",
            ("release", member.id, str(member), ctx.author.id, str(ctx.author), reason)
        )
        conn.commit()
        conn.close()

        # Log
        from utils import send_log
        await send_log(
            self.bot,
            "🔓 Nutzer entlassen",
            f"👤  **Nutzer:** {member} (`{member.id}`)\n"
            f"👮  **Von:** {ctx.author}\n"
            f"📝  **Grund:** {reason}\n"
            f"🎭  **Rollen wiederhergestellt:** {len(roles_to_restore)}",
            discord.Color.from_rgb(34, 197, 94),
        )

        await msg.edit(content=f"🔓 **{member.display_name}** wurde entlassen! Grund: *{reason}*")

    @knast_cmd.command(name="list", aliases=["liste"])
    @has_knast_permission()
    async def knast_list(self, ctx: commands.Context):
        """Zeigt alle Nutzer im Knast."""
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT user_id, jailed_at, reason FROM knast WHERE guild_id = ?",
            (ctx.guild.id,)
        ).fetchall()
        conn.close()

        if not rows:
            await ctx.send("🔓 Der Knast ist leer.")
            return

        entries = []
        for user_id, jailed_at, reason in rows:
            member = ctx.guild.get_member(user_id)
            name = member.mention if member else f"`{user_id}`"
            date = (jailed_at or "")[:16].replace("T", " ")
            entries.append(f"🔒 {name}\n╰ *{reason or '?'}* — {date}")

        embed = discord.Embed(
            title=f"🔒 Knast — {len(rows)} Insasse{'n' if len(rows) != 1 else ''}",
            description="\n\n".join(entries),
            color=discord.Color.from_rgb(128, 0, 0),
        )
        await ctx.send(embed=embed)

    # ── Events ────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Verhindert, dass Knast-Insassen den Voice-Kanal verlassen."""
        if not self._is_jailed(member.id):
            return
        if after.channel is None:
            return
        settings = _load_knast_settings()
        jail_cat_id = settings.get("knast_category")
        if not jail_cat_id:
            return
        if after.channel.category_id != int(jail_cat_id):
            jail_voice_id = settings.get("knast_voice_channel")
            jail_voice = member.guild.get_channel(int(jail_voice_id)) if jail_voice_id else None
            try:
                if jail_voice:
                    await member.move_to(jail_voice, reason="Knast: kein Verlassen erlaubt")
                else:
                    await member.move_to(None, reason="Knast: kein Verlassen erlaubt")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Stellt Knast wieder her wenn ein Insasse den Server verlässt und wieder beitritt."""
        if not self._is_jailed(member.id):
            return
        settings = _load_knast_settings()
        jail_cat = member.guild.get_channel(int(settings.get("knast_category", 0)))
        jail_role_id = settings.get("knast_role")
        jail_role = member.guild.get_role(int(jail_role_id)) if jail_role_id else None
        if not jail_cat or not jail_role:
            return
        try:
            await member.add_roles(jail_role, reason="Knast: Wiederbeitritt")
        except discord.Forbidden:
            pass
        await self._apply_jail(member, jail_cat)


async def setup(bot: commands.Bot):
    await bot.add_cog(KnastCog(bot))
