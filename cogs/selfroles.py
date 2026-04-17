import json
import os
import discord
from discord.ext import commands

SELFROLES_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'selfroles.json')


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
    def __init__(self, role_id: int, emoji_str: str, label: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label[:80],
            emoji=emoji_str or None,
            custom_id=f"selfrole:{role_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.custom_id.split(":")[1])
        role = interaction.guild.get_role(role_id)
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
        for r in roles:
            self.add_item(SelfRoleButton(r["role_id"], r.get("emoji", ""), r["role_name"]))


def _build_embed(roles: list, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🎭 Selbst-Rollen",
        color=discord.Color.from_rgb(88, 101, 242),
    )
    if roles:
        lines = []
        for r in roles:
            role = guild.get_role(r["role_id"])
            emoji = r.get("emoji") or "•"
            desc  = r.get("description") or ""
            name  = role.name if role else r["role_name"]
            lines.append(f"{emoji} **{name}**" + (f" — {desc}" if desc else ""))
        embed.description = (
            "Klicke auf einen Button um eine Rolle zu erhalten oder zu entfernen.\n\n"
            + "\n".join(lines)
        )
    else:
        embed.description = "Noch keine Rollen konfiguriert."
    embed.set_footer(text="Klicke einen Button • Erneut klicken um die Rolle zu entfernen")
    return embed


# ── Cog ───────────────────────────────────────────────────────────────────────

class SelfRolesCog(commands.Cog, name="SelfRoles"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        """Persistente Views beim Start registrieren."""
        for guild_id_str, cfg in _load().items():
            roles = cfg.get("roles", [])
            if roles:
                self.bot.add_view(SelfRoleView(roles))

    async def send_or_update_panel(self, guild: discord.Guild) -> bool:
        """Sendet oder aktualisiert das Panel im konfigurierten Channel."""
        cfg       = get_cfg(guild.id)
        roles     = cfg.get("roles", [])
        ch_id     = cfg.get("panel_channel_id")
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
                    "`%selfrole list` — Alle Selfroles anzeigen"
                ),
                color=discord.Color.blurple(),
            )
            await ctx.send(embed=embed)

    @selfrole_cmd.command(name="add")
    async def sr_add(self, ctx, role: discord.Role, emoji: str = "", *, description: str = ""):
        cfg = get_cfg(ctx.guild.id)
        if any(r["role_id"] == role.id for r in cfg["roles"]):
            await ctx.send(f"❌ **{role.name}** ist bereits als Selfrole konfiguriert.")
            return
        cfg["roles"].append({
            "role_id":     role.id,
            "role_name":   role.name,
            "emoji":       emoji,
            "description": description,
        })
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
        if ok:
            await ctx.send(f"✅ Panel in {channel.mention} gesendet.")
        else:
            await ctx.send("❌ Fehler beim Senden.")

    @selfrole_cmd.command(name="list")
    async def sr_list(self, ctx):
        cfg   = get_cfg(ctx.guild.id)
        roles = cfg.get("roles", [])
        if not roles:
            await ctx.send("Keine Selfroles konfiguriert.")
            return
        lines = [
            f"{r.get('emoji') or '•'} **{r['role_name']}**"
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
