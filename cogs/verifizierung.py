import discord
import json
import sqlite3
import os
from discord.ext import commands

VERIFY_CHANNEL_ID  = 1494483085687914657
TICKET_CATEGORY_ID = 1494482692039774331
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')


def _get_mod_roles() -> list[int]:
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT value FROM bot_settings WHERE key = 'ticket_mod_roles'"
        ).fetchone()
        conn.close()
        return json.loads(row[0]) if row else []
    except Exception:
        return []


def _save_mod_roles(role_ids: list[int]):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO bot_settings (key, value) VALUES ('ticket_mod_roles', ?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (json.dumps(role_ids),)
    )
    conn.commit()
    conn.close()


def _get_verify_text() -> tuple[str, str]:
    """Gibt (titel, beschreibung) des Verifizierungs-Embeds zurück."""
    defaults = (
        "✅ Verifizierung",
        "Klicke auf den Button unten, um ein Ticket zu öffnen.\n"
        "Ein Moderator wird dich dann verifizieren.\n\n"
        "🎫 **Ticket erstellen** → Button drücken",
    )
    try:
        conn = sqlite3.connect(DB_PATH)
        title = conn.execute(
            "SELECT value FROM bot_settings WHERE key = 'verify_title'"
        ).fetchone()
        desc = conn.execute(
            "SELECT value FROM bot_settings WHERE key = 'verify_description'"
        ).fetchone()
        conn.close()
        return (
            json.loads(title[0]) if title else defaults[0],
            json.loads(desc[0])  if desc  else defaults[1],
        )
    except Exception:
        return defaults


def _get_ticket_text() -> tuple[str, str]:
    """Gibt (titel, beschreibung) der Ticket-Willkommensnachricht zurück."""
    defaults = (
        "🎫 Verifizierungs-Ticket",
        "Willkommen {mention}!\n\n"
        "Ein Moderator wird sich in Kürze um dein Ticket kümmern.\n"
        "Schreibe hier dein Anliegen oder warte auf weitere Anweisungen.\n\n"
        "Zum Schließen des Tickets den Button unten nutzen.",
    )
    try:
        conn = sqlite3.connect(DB_PATH)
        title = conn.execute(
            "SELECT value FROM bot_settings WHERE key = 'ticket_title'"
        ).fetchone()
        desc = conn.execute(
            "SELECT value FROM bot_settings WHERE key = 'ticket_description'"
        ).fetchone()
        conn.close()
        return (
            json.loads(title[0]) if title else defaults[0],
            json.loads(desc[0])  if desc  else defaults[1],
        )
    except Exception:
        return defaults


def _save_verify_text(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO bot_settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value))
    )
    conn.commit()
    conn.close()


# ── Views ─────────────────────────────────────────────────────────────────────

class VerifyView(discord.ui.View):
    """Persistente View für den Verifizierungs-Button."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ticket erstellen",
        style=discord.ButtonStyle.primary,
        custom_id="verify:open",
        emoji="🎫",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild    = interaction.guild
        user     = interaction.user
        category = guild.get_channel(TICKET_CATEGORY_ID)

        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "❌ Die Ticket-Kategorie wurde nicht gefunden. Bitte kontaktiere einen Admin.",
                ephemeral=True,
            )
            return

        # Bereits ein offenes Ticket?
        existing = discord.utils.get(
            category.channels, name=f"ticket-{user.id}"
        )
        if existing:
            await interaction.response.send_message(
                f"📂 Du hast bereits ein offenes Ticket: {existing.mention}",
                ephemeral=True,
            )
            return

        # Berechtigungen aufbauen
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
            ),
        }
        # Moderatoren-Rollen hinzufügen
        for role_id in _get_mod_roles():
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                )

        # Ticket-Kanal erstellen
        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{user.id}",
                category=category,
                overwrites=overwrites,
                topic=f"Verifizierungs-Ticket von {user} ({user.id})",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Keine Berechtigung, einen Kanal zu erstellen.",
                ephemeral=True,
            )
            return

        # Willkommensnachricht im Ticket
        t_title, t_desc = _get_ticket_text()
        embed = discord.Embed(
            title=t_title,
            description=t_desc.replace("{mention}", user.mention),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User-ID: {user.id}")

        await channel.send(user.mention, embed=embed, view=CloseView())
        await interaction.response.send_message(
            f"✅ Dein Ticket wurde erstellt: {channel.mention}",
            ephemeral=True,
        )


class CloseView(discord.ui.View):
    """Persistente View für den Schließen-Button im Ticket."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ticket schließen",
        style=discord.ButtonStyle.danger,
        custom_id="verify:close",
        emoji="🔒",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel

        # Nur im Ticket-Kanal erlaubt
        if not isinstance(channel, discord.TextChannel):
            return
        if channel.category_id != TICKET_CATEGORY_ID:
            await interaction.response.send_message("❌ Das ist kein Ticket-Kanal.", ephemeral=True)
            return

        # Wer darf schließen? Mod-Rollen oder der Ticket-Ersteller
        user_role_ids = {r.id for r in interaction.user.roles}
        mod_roles = set(_get_mod_roles())
        is_mod = bool(user_role_ids & mod_roles) or interaction.user.guild_permissions.administrator

        # Ticket-Ersteller aus dem Channel-Namen ermitteln
        owner_id = channel.name.replace("ticket-", "")
        is_owner = str(interaction.user.id) == owner_id

        if not is_mod and not is_owner:
            await interaction.response.send_message(
                "❌ Nur der Ticket-Ersteller oder ein Moderator kann das Ticket schließen.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message("🔒 Ticket wird geschlossen…")
        await channel.delete(reason=f"Ticket geschlossen von {interaction.user}")


# ── Cog ───────────────────────────────────────────────────────────────────────

class VerifizierungCog(commands.Cog, name="Verifizierung"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="verifizierung", aliases=["verify", "ticket"], invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def verifizierung_cmd(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎫 Verifizierungs-System",
            description=(
                "**Verifizierungs-Embed (Button-Kanal)**\n"
                "`%verifizierung setup` — Sendet die Verifizierungs-Nachricht\n"
                "`%verifizierung titel <Text>` — Titel des Embeds ändern\n"
                "`%verifizierung text <Text>` — Beschreibung des Embeds ändern\n"
                "`%verifizierung vorschau` — Aktuelle Nachricht anzeigen\n"
                "`%verifizierung modrole @rolle` — Moderatoren-Rolle hinzufügen/entfernen\n\n"
                "**Ticket-Willkommensnachricht (im Ticket)**\n"
                "`%verifizierung tickettitel <Text>` — Titel der Ticket-Nachricht ändern\n"
                "`%verifizierung tickettext <Text>` — Text der Ticket-Nachricht ändern\n"
                "`%verifizierung ticketvorschau` — Ticket-Nachricht-Vorschau anzeigen\n"
                "_(Tipp: `{mention}` wird durch den Nutzernamen ersetzt)_"
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        await ctx.send(embed=embed)

    @verifizierung_cmd.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def verifizierung_setup(self, ctx: commands.Context):
        """Sendet die Verifizierungs-Nachricht in den konfigurierten Kanal."""
        channel = self.bot.get_channel(VERIFY_CHANNEL_ID)
        if not channel:
            await ctx.send(f"❌ Kanal `{VERIFY_CHANNEL_ID}` nicht gefunden.")
            return

        title, description = _get_verify_text()
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_footer(text="Pink Horizoon Bot · Verifizierungs-System")

        await channel.send(embed=embed, view=VerifyView())
        await ctx.send(f"✅ Verifizierungs-Nachricht wurde in {channel.mention} gesendet!")

    @verifizierung_cmd.command(name="titel")
    @commands.has_permissions(administrator=True)
    async def verifizierung_titel(self, ctx: commands.Context, *, titel: str):
        """Ändert den Titel des Verifizierungs-Embeds.
        Beispiel: %verifizierung titel ✅ Willkommen – Verifizierung"""
        _save_verify_text("verify_title", titel)
        await ctx.send(f"✅ Titel gespeichert: **{titel}**\nMit `%verifizierung setup` neu posten.")

    @verifizierung_cmd.command(name="text")
    @commands.has_permissions(administrator=True)
    async def verifizierung_text(self, ctx: commands.Context, *, text: str):
        """Ändert die Beschreibung des Verifizierungs-Embeds.
        Zeilenumbrüche mit \\n einfügen.
        Beispiel: %verifizierung text Drücke den Button um dich zu verifizieren!"""
        text = text.replace("\\n", "\n")
        _save_verify_text("verify_description", text)
        await ctx.send(f"✅ Text gespeichert.\nMit `%verifizierung setup` neu posten.")

    @verifizierung_cmd.command(name="vorschau")
    @commands.has_permissions(administrator=True)
    async def verifizierung_vorschau(self, ctx: commands.Context):
        """Zeigt eine Vorschau der aktuellen Verifizierungs-Nachricht."""
        title, description = _get_verify_text()
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_footer(text="Pink Horizoon Bot · Verifizierungs-System  |  Vorschau")
        await ctx.send("👁️ Vorschau:", embed=embed)

    @verifizierung_cmd.command(name="tickettitel")
    @commands.has_permissions(administrator=True)
    async def verifizierung_tickettitel(self, ctx: commands.Context, *, titel: str):
        """Ändert den Titel der Ticket-Willkommensnachricht.
        Beispiel: %verifizierung tickettitel 🎫 Dein Ticket"""
        _save_verify_text("ticket_title", titel)
        await ctx.send(f"✅ Ticket-Titel gespeichert: **{titel}**")

    @verifizierung_cmd.command(name="tickettext")
    @commands.has_permissions(administrator=True)
    async def verifizierung_tickettext(self, ctx: commands.Context, *, text: str):
        """Ändert den Text der Ticket-Willkommensnachricht.
        Zeilenumbrüche mit \\n, Nutzer-Erwähnung mit {mention}.
        Beispiel: %verifizierung tickettext Willkommen {mention}!\\nEin Mod meldet sich."""
        text = text.replace("\\n", "\n")
        _save_verify_text("ticket_description", text)
        await ctx.send("✅ Ticket-Text gespeichert.\n_(Tipp: `{mention}` wird durch den Nutzernamen ersetzt)_")

    @verifizierung_cmd.command(name="ticketvorschau")
    @commands.has_permissions(administrator=True)
    async def verifizierung_ticketvorschau(self, ctx: commands.Context):
        """Zeigt eine Vorschau der Ticket-Willkommensnachricht."""
        t_title, t_desc = _get_ticket_text()
        embed = discord.Embed(
            title=t_title,
            description=t_desc.replace("{mention}", ctx.author.mention),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"User-ID: {ctx.author.id}  |  Vorschau")
        await ctx.send("👁️ Ticket-Vorschau:", embed=embed)

    @verifizierung_cmd.command(name="modrole")
    @commands.has_permissions(administrator=True)
    async def verifizierung_modrole(self, ctx: commands.Context, role: discord.Role):
        """Fügt eine Moderatoren-Rolle hinzu oder entfernt sie (Toggle)."""
        roles = _get_mod_roles()
        if role.id in roles:
            roles.remove(role.id)
            action = "entfernt"
            color = discord.Color.orange()
        else:
            roles.append(role.id)
            action = "hinzugefügt"
            color = discord.Color.green()
        _save_mod_roles(roles)
        embed = discord.Embed(
            description=f"Rolle {role.mention} wurde als Moderatoren-Rolle **{action}**.",
            color=color,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    # Persistente Views registrieren (überlebt Bot-Neustarts)
    bot.add_view(VerifyView())
    bot.add_view(CloseView())
    await bot.add_cog(VerifizierungCog(bot))
