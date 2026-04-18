import discord
import json
import sqlite3
import os
import sys
from discord.ext import commands

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import send_log

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')

COLORS = {
    "boys":  discord.Color.from_rgb(88,  101, 242),
    "girls": discord.Color.from_rgb(236, 72,  153),
}

DEFAULTS = {
    "boys": {
        "verify_channel":     1494483085687914657,
        "ticket_category":    1494482692039774331,
        "verify_title":       "✅ Boys-Verifizierung",
        "verify_description": (
            "Klicke auf den Button unten, um ein Ticket zu öffnen.\n"
            "Ein Moderator wird dich dann verifizieren.\n\n"
            "🎫 **Ticket erstellen** → Button drücken"
        ),
        "ticket_title":       "🎫 Boys-Verifizierungs-Ticket",
        "ticket_description": (
            "Willkommen {mention}!\n\n"
            "Ein Moderator wird sich in Kürze um dein Ticket kümmern.\n"
            "Schreibe hier dein Anliegen oder warte auf weitere Anweisungen.\n\n"
            "Zum Schließen des Tickets den Button unten nutzen."
        ),
        "mod_roles": [],
    },
    "girls": {
        "verify_channel":     0,
        "ticket_category":    0,
        "verify_title":       "✅ Girls-Verifizierung",
        "verify_description": (
            "Klicke auf den Button unten, um ein Ticket zu öffnen.\n"
            "Ein Moderator wird dich dann verifizieren.\n\n"
            "🎫 **Ticket erstellen** → Button drücken"
        ),
        "ticket_title":       "🎫 Girls-Verifizierungs-Ticket",
        "ticket_description": (
            "Willkommen {mention}!\n\n"
            "Ein Moderator wird sich in Kürze um dein Ticket kümmern.\n"
            "Schreibe hier dein Anliegen oder warte auf weitere Anweisungen.\n\n"
            "Zum Schließen des Tickets den Button unten nutzen."
        ),
        "mod_roles": [],
    },
}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get(key: str, default=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute("SELECT value FROM bot_settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return json.loads(row[0]) if row else default
    except Exception:
        return default


def _set(key: str, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO bot_settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value))
    )
    conn.commit()
    conn.close()


def _get_verify_channel(prefix: str) -> int:
    return _get(f"{prefix}_verify_channel", DEFAULTS[prefix]["verify_channel"])

def _get_ticket_category(prefix: str) -> int:
    return _get(f"{prefix}_ticket_category", DEFAULTS[prefix]["ticket_category"])

def _get_verify_text(prefix: str) -> tuple[str, str]:
    return (
        _get(f"{prefix}_verify_title",       DEFAULTS[prefix]["verify_title"]),
        _get(f"{prefix}_verify_description", DEFAULTS[prefix]["verify_description"]),
    )

def _get_ticket_text(prefix: str) -> tuple[str, str]:
    return (
        _get(f"{prefix}_ticket_title",       DEFAULTS[prefix]["ticket_title"]),
        _get(f"{prefix}_ticket_description", DEFAULTS[prefix]["ticket_description"]),
    )

def _get_mod_roles(prefix: str) -> list[int]:
    return _get(f"{prefix}_mod_roles", [])


# ── Shared ticket logic ───────────────────────────────────────────────────────

async def _do_open_ticket(interaction: discord.Interaction, prefix: str):
    guild    = interaction.guild
    user     = interaction.user
    cat_id   = _get_ticket_category(prefix)
    category = guild.get_channel(cat_id)
    color    = COLORS[prefix]
    label    = "Boys" if prefix == "boys" else "Girls"

    if not category or not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message(
            "❌ Die Ticket-Kategorie wurde nicht gefunden. Bitte kontaktiere einen Admin.",
            ephemeral=True,
        )
        return

    existing = discord.utils.get(category.channels, name=f"ticket-{user.id}")
    if existing:
        await interaction.response.send_message(
            f"📂 Du hast bereits ein offenes Ticket: {existing.mention}",
            ephemeral=True,
        )
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True,
            read_message_history=True, attach_files=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True,
        ),
    }
    for role_id in _get_mod_roles(prefix):
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, manage_messages=True,
            )

    try:
        channel = await guild.create_text_channel(
            name=f"ticket-{user.id}",
            category=category,
            overwrites=overwrites,
            topic=f"{label}-Verifizierungs-Ticket von {user} ({user.id})",
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Keine Berechtigung, einen Kanal zu erstellen.", ephemeral=True,
        )
        return

    t_title, t_desc = _get_ticket_text(prefix)
    embed = discord.Embed(
        title=t_title,
        description=t_desc.replace("{mention}", user.mention),
        color=color,
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text=f"User-ID: {user.id}")

    close_view = BoysCloseView() if prefix == "boys" else GirlsCloseView()
    await channel.send(user.mention, embed=embed, view=close_view)
    await interaction.response.send_message(
        f"✅ Dein Ticket wurde erstellt: {channel.mention}", ephemeral=True,
    )
    await send_log(
        interaction.client,
        f"🎫 {label}-Ticket erstellt",
        f"👤  **Nutzer:** {user.mention} (`{user.id}`)\n"
        f"📂  **Kanal:** {channel.mention}",
    )


async def _do_close_ticket(interaction: discord.Interaction, prefix: str):
    channel = interaction.channel
    cat_id  = _get_ticket_category(prefix)
    label   = "Boys" if prefix == "boys" else "Girls"

    if not isinstance(channel, discord.TextChannel):
        return
    if channel.category_id != cat_id:
        await interaction.response.send_message("❌ Das ist kein Ticket-Kanal.", ephemeral=True)
        return

    user_role_ids = {r.id for r in interaction.user.roles}
    is_mod  = bool(user_role_ids & set(_get_mod_roles(prefix))) or \
              interaction.user.guild_permissions.administrator
    is_owner = str(interaction.user.id) == channel.name.replace("ticket-", "")

    if not is_mod and not is_owner:
        await interaction.response.send_message(
            "❌ Nur der Ticket-Ersteller oder ein Moderator kann das Ticket schließen.",
            ephemeral=True,
        )
        return

    await send_log(
        interaction.client,
        f"🔒 {label}-Ticket geschlossen",
        f"👤  **Von:** {interaction.user.mention} (`{interaction.user.id}`)\n"
        f"📂  **Kanal:** `#{channel.name}`\n"
        f"🔑  **Rolle:** {'Moderator' if is_mod else 'Ticket-Ersteller'}",
    )
    await interaction.response.send_message("🔒 Ticket wird geschlossen…")
    await channel.delete(reason=f"Ticket geschlossen von {interaction.user}")


# ── Views ─────────────────────────────────────────────────────────────────────

class BoysVerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket erstellen", style=discord.ButtonStyle.primary,
                       custom_id="verify:open:boys", emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_open_ticket(interaction, "boys")


class GirlsVerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket erstellen", style=discord.ButtonStyle.danger,
                       custom_id="verify:open:girls", emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_open_ticket(interaction, "girls")


class BoysCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket schließen", style=discord.ButtonStyle.danger,
                       custom_id="verify:close:boys", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_close_ticket(interaction, "boys")


class GirlsCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ticket schließen", style=discord.ButtonStyle.danger,
                       custom_id="verify:close:girls", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _do_close_ticket(interaction, "girls")


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
                "Verwende `boys` oder `girls` als zweites Argument:\n\n"
                "`%verifizierung boys setup` — Boys-Embed in den konfigurierten Kanal senden\n"
                "`%verifizierung boys titel <Text>` — Titel des Embeds setzen\n"
                "`%verifizierung boys text <Text>` — Beschreibung setzen\n"
                "`%verifizierung boys vorschau` — Vorschau anzeigen\n"
                "`%verifizierung boys tickettitel <Text>` — Ticket-Titel setzen\n"
                "`%verifizierung boys tickettext <Text>` — Ticket-Text setzen (`{mention}` → Nutzer)\n"
                "`%verifizierung boys ticketvorschau` — Ticket-Vorschau anzeigen\n"
                "`%verifizierung boys modrole @Rolle` — Moderatoren-Rolle hinzufügen/entfernen\n\n"
                "Genauso für `girls`."
            ),
            color=discord.Color.from_rgb(88, 101, 242),
        )
        await ctx.send(embed=embed)

    # ── Boys ──────────────────────────────────────────────────────────────────

    @verifizierung_cmd.group(name="boys", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def boys(self, ctx):
        await ctx.send("Befehle: `setup`, `titel`, `text`, `vorschau`, `tickettitel`, `tickettext`, `ticketvorschau`, `modrole`")

    @boys.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def boys_setup(self, ctx):
        await self._send_setup(ctx, "boys")

    @boys.command(name="titel")
    @commands.has_permissions(administrator=True)
    async def boys_titel(self, ctx, *, titel: str):
        _set("boys_verify_title", titel)
        await ctx.send(f"✅ Boys-Embed-Titel gespeichert: **{titel}**")

    @boys.command(name="text")
    @commands.has_permissions(administrator=True)
    async def boys_text(self, ctx, *, text: str):
        _set("boys_verify_description", text.replace("\\n", "\n"))
        await ctx.send("✅ Boys-Embed-Text gespeichert.")

    @boys.command(name="vorschau")
    @commands.has_permissions(administrator=True)
    async def boys_vorschau(self, ctx):
        await self._send_vorschau(ctx, "boys")

    @boys.command(name="tickettitel")
    @commands.has_permissions(administrator=True)
    async def boys_tickettitel(self, ctx, *, titel: str):
        _set("boys_ticket_title", titel)
        await ctx.send(f"✅ Boys-Ticket-Titel gespeichert: **{titel}**")

    @boys.command(name="tickettext")
    @commands.has_permissions(administrator=True)
    async def boys_tickettext(self, ctx, *, text: str):
        _set("boys_ticket_description", text.replace("\\n", "\n"))
        await ctx.send("✅ Boys-Ticket-Text gespeichert. _(Tipp: `{mention}` → Nutzername)_")

    @boys.command(name="ticketvorschau")
    @commands.has_permissions(administrator=True)
    async def boys_ticketvorschau(self, ctx):
        await self._send_ticketvorschau(ctx, "boys")

    @boys.command(name="modrole")
    @commands.has_permissions(administrator=True)
    async def boys_modrole(self, ctx, role: discord.Role):
        await self._toggle_modrole(ctx, "boys", role)

    # ── Girls ─────────────────────────────────────────────────────────────────

    @verifizierung_cmd.group(name="girls", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def girls(self, ctx):
        await ctx.send("Befehle: `setup`, `titel`, `text`, `vorschau`, `tickettitel`, `tickettext`, `ticketvorschau`, `modrole`")

    @girls.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def girls_setup(self, ctx):
        await self._send_setup(ctx, "girls")

    @girls.command(name="titel")
    @commands.has_permissions(administrator=True)
    async def girls_titel(self, ctx, *, titel: str):
        _set("girls_verify_title", titel)
        await ctx.send(f"✅ Girls-Embed-Titel gespeichert: **{titel}**")

    @girls.command(name="text")
    @commands.has_permissions(administrator=True)
    async def girls_text(self, ctx, *, text: str):
        _set("girls_verify_description", text.replace("\\n", "\n"))
        await ctx.send("✅ Girls-Embed-Text gespeichert.")

    @girls.command(name="vorschau")
    @commands.has_permissions(administrator=True)
    async def girls_vorschau(self, ctx):
        await self._send_vorschau(ctx, "girls")

    @girls.command(name="tickettitel")
    @commands.has_permissions(administrator=True)
    async def girls_tickettitel(self, ctx, *, titel: str):
        _set("girls_ticket_title", titel)
        await ctx.send(f"✅ Girls-Ticket-Titel gespeichert: **{titel}**")

    @girls.command(name="tickettext")
    @commands.has_permissions(administrator=True)
    async def girls_tickettext(self, ctx, *, text: str):
        _set("girls_ticket_description", text.replace("\\n", "\n"))
        await ctx.send("✅ Girls-Ticket-Text gespeichert. _(Tipp: `{mention}` → Nutzername)_")

    @girls.command(name="ticketvorschau")
    @commands.has_permissions(administrator=True)
    async def girls_ticketvorschau(self, ctx):
        await self._send_ticketvorschau(ctx, "girls")

    @girls.command(name="modrole")
    @commands.has_permissions(administrator=True)
    async def girls_modrole(self, ctx, role: discord.Role):
        await self._toggle_modrole(ctx, "girls", role)

    # ── Shared helpers ────────────────────────────────────────────────────────

    async def _send_setup(self, ctx, prefix: str):
        label   = "Boys" if prefix == "boys" else "Girls"
        ch_id   = _get_verify_channel(prefix)
        channel = self.bot.get_channel(ch_id)
        if not channel:
            await ctx.send(f"❌ Kanal-ID `{ch_id}` nicht gefunden. Bitte im Dashboard konfigurieren.")
            return
        title, description = _get_verify_text(prefix)
        embed = discord.Embed(title=title, description=description, color=COLORS[prefix])
        embed.set_footer(text=f"Pink Horizoon Bot · {label}-Verifizierung")
        view = BoysVerifyView() if prefix == "boys" else GirlsVerifyView()
        await channel.send(embed=embed, view=view)
        await ctx.send(f"✅ {label}-Verifizierungs-Nachricht wurde in {channel.mention} gesendet!")

    async def _send_vorschau(self, ctx, prefix: str):
        label = "Boys" if prefix == "boys" else "Girls"
        title, description = _get_verify_text(prefix)
        embed = discord.Embed(title=title, description=description, color=COLORS[prefix])
        embed.set_footer(text=f"Pink Horizoon Bot · {label}-Verifizierung  |  Vorschau")
        await ctx.send("👁️ Vorschau:", embed=embed)

    async def _send_ticketvorschau(self, ctx, prefix: str):
        t_title, t_desc = _get_ticket_text(prefix)
        embed = discord.Embed(
            title=t_title,
            description=t_desc.replace("{mention}", ctx.author.mention),
            color=COLORS[prefix],
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text=f"User-ID: {ctx.author.id}  |  Vorschau")
        await ctx.send("👁️ Ticket-Vorschau:", embed=embed)

    async def _toggle_modrole(self, ctx, prefix: str, role: discord.Role):
        roles = _get_mod_roles(prefix)
        if role.id in roles:
            roles.remove(role.id)
            action = "entfernt"
            color  = discord.Color.orange()
        else:
            roles.append(role.id)
            action = "hinzugefügt"
            color  = discord.Color.green()
        _set(f"{prefix}_mod_roles", roles)
        await ctx.send(embed=discord.Embed(
            description=f"Rolle {role.mention} wurde als Moderatoren-Rolle **{action}**.",
            color=color,
        ))


async def setup(bot: commands.Bot):
    bot.add_view(BoysVerifyView())
    bot.add_view(GirlsVerifyView())
    bot.add_view(BoysCloseView())
    bot.add_view(GirlsCloseView())
    await bot.add_cog(VerifizierungCog(bot))
