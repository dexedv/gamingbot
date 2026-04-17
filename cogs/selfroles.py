import json
import os
import re
import discord
from discord.ext import commands

SELFROLES_PATH  = os.path.join(os.path.dirname(__file__), '..', 'data', 'selfroles.json')
IMPORT_CHANNEL  = 1019594993226219610   # Channel der beim Start automatisch gescannt wird


def _load() -> dict:
    try:
        with open(SELFROLES_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(SELFROLES_PATH), exist_ok=True)
    with open(SELFROLES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_cfg(guild_id: int) -> dict:
    return _load().get(str(guild_id), {
        "roles": [], "panel_channel_id": None, "panel_message_id": None
    })


def set_cfg(guild_id: int, cfg: dict):
    data = _load()
    data[str(guild_id)] = cfg
    _save(data)


# ── UI ────────────────────────────────────────────────────────────────────────

class SelfRoleButton(discord.ui.Button):
    def __init__(self, role_id: int, emoji_str: str, label: str, index: int = 0):
        styles = [
            discord.ButtonStyle.primary,
            discord.ButtonStyle.success,
            discord.ButtonStyle.secondary,
        ]
        super().__init__(
            style=styles[index % len(styles)],
            label=label[:80],
            emoji=emoji_str or None,
            custom_id=f"selfrole:{role_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.custom_id.split(":")[1])
        role    = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("❌ Rolle nicht gefunden.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"✅ Rolle **{role.name}** entfernt.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"✅ Rolle **{role.name}** hinzugefügt.", ephemeral=True)


class SelfRoleView(discord.ui.View):
    def __init__(self, roles: list):
        super().__init__(timeout=None)
        for i, r in enumerate(roles):
            self.add_item(SelfRoleButton(r["role_id"], r.get("emoji", ""), r["role_name"], i))


def _build_embed(roles: list, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🎭 Selbst-Rollen wählen",
        color=discord.Color.from_rgb(88, 101, 242),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    if roles:
        lines = []
        for r in roles:
            role  = guild.get_role(r["role_id"])
            emoji = r.get("emoji") or "▪️"
            desc  = r.get("description") or ""
            name  = role.name if role else r["role_name"]
            lines.append(f"{emoji} **{name}**" + (f"\n╰ {desc}" if desc else ""))

        embed.description = (
            "Klicke auf einen Button um eine Rolle zu erhalten.\n"
            "Erneut klicken entfernt die Rolle wieder.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            + "\n\n".join(lines)
        )
    else:
        embed.description = "Noch keine Rollen konfiguriert."

    embed.set_footer(text=f"{guild.name} · Klicke einen Button · Erneut klicken zum Entfernen")
    return embed


# ── Scan-Hilfsfunktion ────────────────────────────────────────────────────────

async def scan_channel(channel: discord.TextChannel) -> list[dict]:
    """
    Scannt einen Channel nach Selfrole-Nachrichten.
    Erkennt: Rollenmention <@&ID>, Button-custom_ids, Button-Labels (Namensabgleich).
    Gibt eine Liste mit role_id, role_name, emoji, description zurück.
    """
    guild    = channel.guild
    found    = []
    seen_ids : set[int] = set()

    def _add(role: discord.Role, emoji: str = "", desc: str = ""):
        if role.id not in seen_ids and not role.is_default() and not role.managed:
            found.append({
                "role_id":     role.id,
                "role_name":   role.name,
                "emoji":       emoji,
                "description": desc,
            })
            seen_ids.add(role.id)

    # Rollenname-Index für Namensabgleich
    role_by_name = {r.name.lower(): r for r in guild.roles if not r.is_default() and not r.managed}

    async for msg in channel.history(limit=50, oldest_first=True):
        # Rollenerwähnungen im Content und Embeds
        texts = [msg.content]
        for emb in msg.embeds:
            texts.append(emb.description or "")
            for field in emb.fields:
                texts.append(field.value)
        for text in texts:
            for rid_str in re.findall(r"<@&(\d+)>", text):
                role = guild.get_role(int(rid_str))
                if role:
                    _add(role)

        # Buttons scannen
        for row in msg.components:
            buttons = getattr(row, "children", [row])
            for btn in buttons:
                if not hasattr(btn, "label"):
                    continue
                label     = (btn.label or "").strip()
                custom_id = getattr(btn, "custom_id", "") or ""
                emoji_str = str(btn.emoji) if getattr(btn, "emoji", None) else ""

                # custom_id → Rollen-ID
                matched_via_id = False
                for part in custom_id.split(":"):
                    try:
                        rid  = int(part)
                        role = guild.get_role(rid)
                        if role:
                            _add(role, emoji_str)
                            matched_via_id = True
                    except ValueError:
                        pass

                # Label → Rollenname (Fallback)
                if not matched_via_id and label:
                    role = role_by_name.get(label.lower())
                    if role:
                        _add(role, emoji_str)

    return found


# ── Cog ───────────────────────────────────────────────────────────────────────

class SelfRolesCog(commands.Cog, name="SelfRoles"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Persistente Views registrieren + ggf. Auto-Import aus bekanntem Channel."""
        data = _load()

        # Persistente Views für alle gespeicherten Guilds registrieren
        for cfg in data.values():
            if cfg.get("roles"):
                self.bot.add_view(SelfRoleView(cfg["roles"]))

        # Auto-Import: wenn noch keine Selfroles konfiguriert, bekannten Channel scannen
        for guild in self.bot.guilds:
            cfg = data.get(str(guild.id), {})
            if cfg.get("roles"):
                continue   # schon konfiguriert → überspringen

            channel = guild.get_channel(IMPORT_CHANNEL)
            if not channel:
                continue

            try:
                roles = await scan_channel(channel)
                if not roles:
                    continue

                new_cfg = {
                    "roles":             roles,
                    "panel_channel_id":  channel.id,
                    "panel_message_id":  None,
                }
                set_cfg(guild.id, new_cfg)
                self.bot.add_view(SelfRoleView(roles))

                # Neues Panel senden
                await self.send_or_update_panel(guild)

                from utils import send_log
                await send_log(
                    self.bot, "🎭 Selfroles automatisch importiert",
                    f"**Channel:** #{channel.name}\n"
                    f"**Importierte Rollen:** {', '.join(r['role_name'] for r in roles)}",
                    discord.Color.green(),
                )
            except Exception as e:
                from utils import send_log
                await send_log(self.bot, "❌ Selfrole-Import fehlgeschlagen",
                               f"{e}", discord.Color.red())

    async def send_or_update_panel(self, guild: discord.Guild) -> bool:
        cfg     = get_cfg(guild.id)
        roles   = cfg.get("roles", [])
        ch_id   = cfg.get("panel_channel_id")
        if not ch_id:
            return False
        channel = guild.get_channel(int(ch_id))
        if not channel:
            return False

        embed = _build_embed(roles, guild)
        view  = SelfRoleView(roles)

        msg_id = cfg.get("panel_message_id")
        if msg_id:
            try:
                msg = await channel.fetch_message(int(msg_id))
                await msg.edit(embed=embed, view=view)
                self.bot.add_view(view, message_id=int(msg_id))
                return True
            except Exception:
                pass

        msg = await channel.send(embed=embed, view=view)
        self.bot.add_view(view, message_id=msg.id)
        cfg["panel_message_id"] = msg.id
        set_cfg(guild.id, cfg)
        return True

    # ── Discord-Befehle ───────────────────────────────────────────────────────

    @commands.group(name="selfrole", aliases=["sr"])
    @commands.has_permissions(administrator=True)
    async def selfrole_cmd(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="🎭 Selfrole-Befehle",
                description=(
                    "`%selfrole add <@Rolle> [emoji] [beschreibung]` — Rolle hinzufügen\n"
                    "`%selfrole remove <@Rolle>` — Rolle entfernen\n"
                    "`%selfrole panel [#channel]` — Panel senden / aktualisieren\n"
                    "`%selfrole scan [#channel]` — Channel scannen & importieren\n"
                    "`%selfrole list` — Alle Selfroles anzeigen"
                ),
                color=discord.Color.blurple(),
            )
            await ctx.send(embed=embed)

    @selfrole_cmd.command(name="add")
    async def sr_add(self, ctx, role: discord.Role, emoji: str = "", *, description: str = ""):
        cfg = get_cfg(ctx.guild.id)
        if any(r["role_id"] == role.id for r in cfg["roles"]):
            await ctx.send(f"❌ **{role.name}** ist bereits konfiguriert.")
            return
        cfg["roles"].append({"role_id": role.id, "role_name": role.name,
                              "emoji": emoji, "description": description})
        set_cfg(ctx.guild.id, cfg)
        await ctx.send(f"✅ **{role.name}** hinzugefügt.")
        if cfg.get("panel_channel_id"):
            await self.send_or_update_panel(ctx.guild)

    @selfrole_cmd.command(name="remove")
    async def sr_remove(self, ctx, role: discord.Role):
        cfg    = get_cfg(ctx.guild.id)
        before = len(cfg["roles"])
        cfg["roles"] = [r for r in cfg["roles"] if r["role_id"] != role.id]
        if len(cfg["roles"]) == before:
            await ctx.send(f"❌ **{role.name}** ist keine Selfrole.")
            return
        set_cfg(ctx.guild.id, cfg)
        await ctx.send(f"🗑️ **{role.name}** entfernt.")
        if cfg.get("panel_channel_id"):
            await self.send_or_update_panel(ctx.guild)

    @selfrole_cmd.command(name="panel")
    async def sr_panel(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        cfg = get_cfg(ctx.guild.id)
        cfg["panel_channel_id"] = channel.id
        cfg["panel_message_id"] = None
        set_cfg(ctx.guild.id, cfg)
        ok = await self.send_or_update_panel(ctx.guild)
        await ctx.send(f"✅ Panel in {channel.mention} gesendet." if ok else "❌ Fehler.")

    @selfrole_cmd.command(name="scan")
    async def sr_scan(self, ctx, channel: discord.TextChannel = None):
        """Scannt einen Channel nach bestehenden Selfroles und importiert sie."""
        channel = channel or ctx.channel
        msg     = await ctx.send(f"⏳ Scanne {channel.mention}…")
        roles   = await scan_channel(channel)
        if not roles:
            await msg.edit(content="❌ Keine Rollen gefunden.")
            return

        cfg = get_cfg(ctx.guild.id)
        existing_ids = {r["role_id"] for r in cfg["roles"]}
        new_roles    = [r for r in roles if r["role_id"] not in existing_ids]

        cfg["roles"].extend(new_roles)
        cfg["panel_channel_id"] = channel.id
        cfg["panel_message_id"] = None
        set_cfg(ctx.guild.id, cfg)

        await self.send_or_update_panel(ctx.guild)
        names = ", ".join(f"**{r['role_name']}**" for r in new_roles)
        await msg.edit(content=(
            f"✅ {len(new_roles)} neue Rollen importiert: {names or '—'}\n"
            f"Panel in {channel.mention} gesendet."
        ))

    @selfrole_cmd.command(name="list")
    async def sr_list(self, ctx):
        cfg   = get_cfg(ctx.guild.id)
        roles = cfg.get("roles", [])
        if not roles:
            await ctx.send("Keine Selfroles konfiguriert.")
            return
        lines = [
            f"{r.get('emoji') or '▪️'} **{r['role_name']}**"
            + (f" — {r['description']}" if r.get("description") else "")
            for r in roles
        ]
        embed = discord.Embed(
            title="🎭 Selfroles",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(SelfRolesCog(bot))
