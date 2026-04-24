import discord
from discord.ext import commands
import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import send_log

DB_PATH          = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')
RULES_CHANNEL_ID = 1019184912110211103
UNVERIFIED_ROLE_NAME = "Unverifiziert"

DEFAULT_RULE_FIELDS = [
    (
        "I. Respekt & Verhalten",
        "➜ Behandle alle Mitglieder mit Respekt und Höflichkeit.\n"
        "➜ Beleidigungen, Diskriminierung, Hassrede oder Mobbing sind strikt verboten.\n"
        "➜ Provokationen, Trolling oder absichtliches Stören der Community werden nicht toleriert.",
    ),
    (
        "II. Spam & Inhalte",
        "➜ Kein Spam (z. B. wiederholte Nachrichten, unnötige Tags, Capslock-Missbrauch).\n"
        "➜ Keine Werbung ohne vorherige Erlaubnis des Teams.\n"
        "➜ Poste Inhalte nur in den dafür vorgesehenen Channels.\n"
        "➜ Vermeide Off-Topic in themenspezifischen Kanälen.",
    ),
    (
        "III. NSFW & unangemessene Inhalte",
        "➜ NSFW-, pornografische oder verstörende Inhalte sind verboten.\n"
        "➜ Keine gewaltverherrlichenden oder extremistischen Inhalte.",
    ),
    (
        "IV. Datenschutz & Sicherheit",
        "➜ Teile keine privaten Informationen (deine oder die anderer).\n"
        "➜ Scams oder Betrugsversuche führen zum sofortigen Bann.\n"
        "➜ Melde verdächtige Aktivitäten dem Team per Ticket.",
    ),
    (
        "V. Umgang mit Moderation",
        "➜ Folge den Anweisungen des Moderationsteams.\n"
        "➜ Das Ausnutzen von Lücken in den Regeln wird nicht toleriert.\n"
        "➜ Respektiere Entscheidungen – sie dienen dem Schutz der Community.",
    ),
    (
        "VI. Sprache & Kommunikation",
        "➜ Nutze eine angemessene Sprache (keine übermäßigen Beleidigungen oder vulgäre Ausdrucksweise).\n"
        "➜ Vermeide übermäßiges Ping/Tagging von Personen oder Rollen.",
    ),
    (
        "VII. Voice-Chat Regeln",
        "➜ Kein Schreien, Stören oder absichtliches Überlagern anderer.\n"
        "➜ Respektiere die Gespräche anderer Teilnehmer.",
    ),
    (
        "VIII. Namen & Profile",
        "➜ Keine beleidigenden, diskriminierenden oder unangemessenen Namen/Bilder/Bios.\n"
        "➜ Keine Nachahmung von Teammitgliedern oder anderen Nutzern.",
    ),
    (
        "IX. Konsequenzen bei Regelverstößen",
        "➜ Verwarnung.\n"
        "➜ Zeitlich begrenzter Mute/Kick.\n"
        "➜ Permanenter Bann.\n"
        "*(Die Strafe richtet sich nach Schwere des Verstoßes.)*",
    ),
    (
        "X. Sonstiges",
        "➜ Das Team behält sich vor, Regeln jederzeit anzupassen.\n"
        "➜ Unwissenheit schützt nicht vor Strafe.\n"
        "➜ Mit dem Beitritt zum Server akzeptierst du diese Regeln.",
    ),
]


def _load_rules() -> list[tuple[str, str]]:
    """Lädt Regelfelder aus DB; fällt auf Default zurück wenn nicht gesetzt."""
    import json
    try:
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute("SELECT value FROM bot_settings WHERE key='regelwerk_rules'").fetchone()
        conn.close()
        if row:
            data = json.loads(row[0])
            if isinstance(data, list) and data:
                return [(r["title"], r["content"]) for r in data]
    except Exception:
        pass
    return DEFAULT_RULE_FIELDS


# ── View ──────────────────────────────────────────────────────────────────────

class RulesAcceptView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ich akzeptiere die Regeln",
        style=discord.ButtonStyle.success,
        custom_id="rules:accept",
        emoji="✅",
    )
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild  = interaction.guild
        member = interaction.user

        role = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
        if not role:
            await interaction.response.send_message(
                "❌ Die Unverifiziert-Rolle wurde nicht gefunden. Bitte kontaktiere einen Admin.",
                ephemeral=True,
            )
            return

        if role not in member.roles:
            await interaction.response.send_message(
                "✅ Du hast die Regeln bereits akzeptiert!", ephemeral=True
            )
            return

        try:
            await member.remove_roles(role, reason="Regeln akzeptiert")
            # In DB speichern
            try:
                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    "INSERT OR REPLACE INTO verified_users (user_id, username, verified_at)"
                    " VALUES (?, ?, datetime('now'))",
                    (member.id, member.display_name),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            await interaction.response.send_message(
                "🎉 Willkommen! Du hast die Regeln akzeptiert und hast jetzt Zugriff auf den Server.",
                ephemeral=True,
            )
            await send_log(
                interaction.client,
                "✅ Regeln akzeptiert",
                f"👤  **Nutzer:** {member.mention} (`{member.id}`)\n"
                f"🎭  **Rolle entfernt:** {role.name}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Keine Berechtigung, die Rolle zu entfernen. Bitte kontaktiere einen Admin.",
                ephemeral=True,
            )


# ── Cog ───────────────────────────────────────────────────────────────────────

class RegelwerkCog(commands.Cog, name="Regelwerk"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="regelwerk", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def regelwerk_cmd(self, ctx: commands.Context):
        embed = discord.Embed(
            title="📜 Regelwerk-System",
            description=(
                "`%regelwerk setup` — Rolle erstellen & Regeln in den Kanal posten\n"
                "`%regelwerk sperren` — Unverifiziert-Rolle aus allen anderen Kanälen sperren\n"
                "`%regelwerk rolle @Nutzer` — Unverifiziert-Rolle manuell zuweisen\n"
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        await ctx.send(embed=embed)

    @regelwerk_cmd.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def cmd_setup(self, ctx: commands.Context):
        guild = ctx.guild

        # Rolle erstellen oder finden
        role = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
        if not role:
            role = await guild.create_role(
                name=UNVERIFIED_ROLE_NAME,
                color=discord.Color.from_rgb(128, 128, 128),
                hoist=False,
                mentionable=False,
                reason="Regelwerk-System: Unverifiziert-Rolle",
            )
            await ctx.send(f"✅ Rolle **{UNVERIFIED_ROLE_NAME}** erstellt: {role.mention}")
        else:
            await ctx.send(f"ℹ️ Rolle **{UNVERIFIED_ROLE_NAME}** existiert bereits: {role.mention}")

        # Regelwerk-Kanal holen
        channel = guild.get_channel(RULES_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            await ctx.send(f"❌ Kanal `{RULES_CHANNEL_ID}` nicht gefunden!")
            return

        # Kanalrechte: Unverifiziert darf diesen Kanal sehen (nur lesen)
        try:
            await channel.set_permissions(
                role,
                view_channel=True,
                send_messages=False,
                read_message_history=True,
            )
            await ctx.send(f"✅ Kanalrechte gesetzt: {role.mention} → {channel.mention} (nur lesen).")
        except discord.Forbidden:
            await ctx.send("❌ Keine Berechtigung, Kanalrechte zu setzen.")
            return

        # Regeln-Embed bauen und senden
        embed = discord.Embed(
            title="📜 Discord Server Regeln",
            description=(
                "Bitte lies die folgenden Regeln sorgfältig durch.\n"
                "Mit dem Klick auf den Button unten bestätigst du, dass du sie gelesen und akzeptiert hast."
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        for name, value in _load_rules():
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text="Durch den Klick auf ✅ bekommst du Zugang zum Server.")

        view = RulesAcceptView()
        await channel.send(embed=embed, view=view)
        await ctx.send(f"✅ Regeln wurden in {channel.mention} gepostet!")

    @regelwerk_cmd.command(name="sperren")
    @commands.has_permissions(administrator=True)
    async def cmd_sperren(self, ctx: commands.Context):
        """Fügt für alle Kanäle (außer dem Regelwerk-Kanal) einen Deny-Overwrite für Unverifiziert hinzu."""
        guild = ctx.guild
        role  = discord.utils.get(guild.roles, name=UNVERIFIED_ROLE_NAME)
        if not role:
            await ctx.send(
                f"❌ Rolle **{UNVERIFIED_ROLE_NAME}** nicht gefunden. Führe erst `%regelwerk setup` aus."
            )
            return

        msg    = await ctx.send("⏳ Setze Kanalrechte für alle Kanäle…")
        count  = 0
        errors = 0
        for ch in guild.channels:
            if ch.id == RULES_CHANNEL_ID:
                continue
            if isinstance(ch, (discord.TextChannel, discord.VoiceChannel,
                                discord.CategoryChannel, discord.ForumChannel,
                                discord.StageChannel)):
                try:
                    await ch.set_permissions(role, view_channel=False)
                    count += 1
                except discord.Forbidden:
                    errors += 1

        result = f"✅ **{count}** Kanäle für {role.mention} gesperrt."
        if errors:
            result += f" ❌ **{errors}** Kanäle konnten nicht gesperrt werden (fehlende Rechte)."
        await msg.edit(content=result)

    @regelwerk_cmd.command(name="rolle")
    @commands.has_permissions(administrator=True)
    async def cmd_rolle(self, ctx: commands.Context, member: discord.Member):
        """Weist einem Nutzer die Unverifiziert-Rolle manuell zu."""
        role = discord.utils.get(ctx.guild.roles, name=UNVERIFIED_ROLE_NAME)
        if not role:
            await ctx.send(f"❌ Rolle **{UNVERIFIED_ROLE_NAME}** nicht gefunden.")
            return
        await member.add_roles(role, reason=f"Manuell zugewiesen von {ctx.author}")
        await ctx.send(f"✅ {member.mention} hat die Rolle {role.mention} erhalten.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        role = discord.utils.get(member.guild.roles, name=UNVERIFIED_ROLE_NAME)
        if role:
            try:
                await member.add_roles(role, reason="Neu beigetreten – Regeln müssen akzeptiert werden")
            except discord.Forbidden:
                pass


async def setup(bot: commands.Bot):
    bot.add_view(RulesAcceptView())
    await bot.add_cog(RegelwerkCog(bot))
