import json
import os
import discord
from discord.ext import commands
from datetime import datetime

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'templates')


def _ensure_dir():
    os.makedirs(TEMPLATES_DIR, exist_ok=True)


def _serialize_overwrites(overwrites: dict) -> list:
    result = []
    for target, ow in overwrites.items():
        allow, deny = ow.pair()
        result.append({
            "target_id":   target.id,
            "target_type": "role" if isinstance(target, discord.Role) else "member",
            "target_name": getattr(target, "name", str(target.id)),
            "allow":       allow.value,
            "deny":        deny.value,
        })
    return result


def snapshot_guild(guild: discord.Guild) -> dict:
    """Erstellt einen synchronen Snapshot der Guild-Struktur (nutzt Cache)."""
    roles = []
    for role in sorted(guild.roles, key=lambda r: r.position):
        if role.is_default():
            continue
        roles.append({
            "id":          role.id,
            "name":        role.name,
            "color":       role.color.value,
            "permissions": role.permissions.value,
            "position":    role.position,
            "hoist":       role.hoist,
            "mentionable": role.mentionable,
        })

    categories = []
    for cat in sorted(guild.categories, key=lambda c: c.position):
        categories.append({
            "id":         cat.id,
            "name":       cat.name,
            "position":   cat.position,
            "overwrites": _serialize_overwrites(cat.overwrites),
        })

    channels = []
    for ch in sorted(guild.channels, key=lambda c: c.position):
        if isinstance(ch, discord.CategoryChannel):
            continue
        entry = {
            "id":            ch.id,
            "name":          ch.name,
            "position":      ch.position,
            "category_id":   ch.category_id,
            "category_name": ch.category.name if ch.category else None,
            "overwrites":    _serialize_overwrites(ch.overwrites),
        }
        if isinstance(ch, discord.TextChannel):
            entry.update(type="text", topic=ch.topic, slowmode_delay=ch.slowmode_delay, nsfw=ch.is_nsfw())
        elif isinstance(ch, discord.VoiceChannel):
            entry.update(type="voice", bitrate=ch.bitrate, user_limit=ch.user_limit)
        elif isinstance(ch, discord.StageChannel):
            entry.update(type="stage", bitrate=ch.bitrate, user_limit=0)
        elif isinstance(ch, discord.ForumChannel):
            entry.update(type="forum", topic=getattr(ch, "topic", None))
        else:
            entry["type"] = "other"
        channels.append(entry)

    return {
        "guild": {
            "id":                      guild.id,
            "name":                    guild.name,
            "description":             guild.description,
            "verification_level":      guild.verification_level.value,
            "explicit_content_filter": guild.explicit_content_filter.value,
            "afk_timeout":             guild.afk_timeout,
            "preferred_locale":        str(guild.preferred_locale),
        },
        "roles":      roles,
        "categories": categories,
        "channels":   channels,
    }


def save_template(name: str, guild: discord.Guild, created_by: str = "Dashboard") -> dict:
    _ensure_dir()
    data = snapshot_guild(guild)
    data["meta"] = {
        "name":           name,
        "created_at":     datetime.now().isoformat(),
        "created_by":     created_by,
        "guild_name":     guild.name,
        "role_count":     len(data["roles"]),
        "category_count": len(data["categories"]),
        "channel_count":  len(data["channels"]),
    }
    with open(os.path.join(TEMPLATES_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data["meta"]


def list_templates() -> list:
    _ensure_dir()
    result = []
    for fname in sorted(os.listdir(TEMPLATES_DIR), reverse=True):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(TEMPLATES_DIR, fname), encoding="utf-8") as f:
                meta = json.load(f).get("meta", {})
            meta.setdefault("name", fname[:-5])
            result.append(meta)
        except Exception:
            result.append({"name": fname[:-5]})
    return result


def load_template(name: str) -> dict:
    with open(os.path.join(TEMPLATES_DIR, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def delete_template(name: str) -> bool:
    path = os.path.join(TEMPLATES_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


class TemplatesCog(commands.Cog, name="Templates"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def restore(self, guild: discord.Guild, data: dict) -> dict:
        """Stellt ein Template wieder her. Gibt Statistiken zurück."""
        created_roles    = 0
        created_cats     = 0
        created_channels = 0
        updated_channels = 0

        existing_roles = {r.name: r for r in guild.roles}
        cat_id_map: dict[int, discord.CategoryChannel] = {}

        # Rollen erstellen
        for rd in data.get("roles", []):
            if rd["name"] not in existing_roles:
                try:
                    role = await guild.create_role(
                        name=rd["name"],
                        color=discord.Color(rd["color"]),
                        permissions=discord.Permissions(rd["permissions"]),
                        hoist=rd["hoist"],
                        mentionable=rd["mentionable"],
                    )
                    existing_roles[rd["name"]] = role
                    created_roles += 1
                except Exception:
                    pass

        # Kategorien erstellen
        existing_cats = {c.name: c for c in guild.categories}
        for cd in data.get("categories", []):
            if cd["name"] in existing_cats:
                cat_id_map[cd["id"]] = existing_cats[cd["name"]]
            else:
                try:
                    cat = await guild.create_category(name=cd["name"], position=cd["position"])
                    cat_id_map[cd["id"]] = cat
                    existing_cats[cd["name"]] = cat
                    created_cats += 1
                except Exception:
                    pass

        # Channels erstellen / aktualisieren
        existing_ch = {c.name: c for c in guild.channels if not isinstance(c, discord.CategoryChannel)}
        for ch in data.get("channels", []):
            ch_type = ch.get("type", "text")
            if ch_type == "other":
                continue
            name     = ch["name"]
            category = cat_id_map.get(ch.get("category_id"))
            if not category and ch.get("category_name"):
                category = existing_cats.get(ch["category_name"])

            if name in existing_ch:
                obj = existing_ch[name]
                try:
                    if isinstance(obj, discord.TextChannel) and ch_type == "text":
                        await obj.edit(
                            topic=ch.get("topic") or "",
                            slowmode_delay=ch.get("slowmode_delay", 0),
                            nsfw=ch.get("nsfw", False),
                        )
                        updated_channels += 1
                except Exception:
                    pass
            else:
                try:
                    if ch_type == "text":
                        new = await guild.create_text_channel(
                            name=name, category=category,
                            topic=ch.get("topic") or "",
                            slowmode_delay=ch.get("slowmode_delay", 0),
                            nsfw=ch.get("nsfw", False),
                        )
                    elif ch_type in ("voice", "stage"):
                        new = await guild.create_voice_channel(
                            name=name, category=category,
                            bitrate=min(ch.get("bitrate", 64000), guild.bitrate_limit),
                            user_limit=ch.get("user_limit", 0),
                        )
                    elif ch_type == "forum":
                        new = await guild.create_forum(name=name, category=category)
                    else:
                        continue
                    existing_ch[name] = new
                    created_channels += 1
                except Exception:
                    pass

        return {
            "created_roles":    created_roles,
            "created_cats":     created_cats,
            "created_channels": created_channels,
            "updated_channels": updated_channels,
        }

    # ── Discord-Commands ──────────────────────────────────────────────────────

    @commands.group(name="template", aliases=["vorlage"])
    @commands.has_permissions(administrator=True)
    async def template_cmd(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="📋 Template-Befehle",
                description=(
                    "`%template create [name]` — Server-Template erstellen\n"
                    "`%template list` — Alle Templates anzeigen\n"
                    "`%template restore <name>` — Template wiederherstellen\n"
                    "`%template delete <name>` — Template löschen"
                ),
                color=discord.Color.blurple(),
            )
            await ctx.send(embed=embed)

    @template_cmd.command(name="create", aliases=["erstellen"])
    async def template_create(self, ctx, *, name: str = None):
        if not name:
            name = datetime.now().strftime("%Y-%m-%d_%H-%M")
        name = name.replace(" ", "_").replace("/", "-")[:50]
        msg = await ctx.send(f"⏳ Erstelle Template **{name}**…")
        try:
            meta = save_template(name, ctx.guild, str(ctx.author))
            from utils import send_log
            await send_log(
                self.bot, "📋 Template erstellt",
                f"**Name:** {name} | **Von:** {ctx.author}\n"
                f"Rollen: {meta['role_count']} | Kategorien: {meta['category_count']} | Channels: {meta['channel_count']}",
                discord.Color.blurple(),
            )
            await msg.edit(content=(
                f"✅ Template **{name}** erstellt!\n"
                f"📊 {meta['role_count']} Rollen | {meta['category_count']} Kategorien | {meta['channel_count']} Channels"
            ))
        except Exception as e:
            await msg.edit(content=f"❌ Fehler: {e}")

    @template_cmd.command(name="list", aliases=["liste"])
    async def template_list(self, ctx):
        tpls = list_templates()
        if not tpls:
            await ctx.send("Keine Templates vorhanden.")
            return
        lines = []
        for t in tpls:
            dt = (t.get("created_at") or "")[:16].replace("T", " ")
            lines.append(
                f"📋 **{t['name']}** — {dt or '?'} von {t.get('created_by','?')}\n"
                f"   {t.get('role_count','?')} Rollen | {t.get('category_count','?')} Kategorien | {t.get('channel_count','?')} Channels"
            )
        embed = discord.Embed(
            title="📋 Server-Templates",
            description="\n\n".join(lines),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    @template_cmd.command(name="restore", aliases=["wiederherstellen"])
    @commands.has_permissions(administrator=True)
    async def template_restore(self, ctx, *, name: str):
        path = os.path.join(TEMPLATES_DIR, f"{name}.json")
        if not os.path.exists(path):
            await ctx.send(f"❌ Template **{name}** nicht gefunden. Nutze `%template list`.")
            return
        data = load_template(name)
        msg = await ctx.send(f"⏳ Stelle Template **{name}** wieder her…")
        try:
            stats = await self.restore(ctx.guild, data)
            from utils import send_log
            await send_log(
                self.bot, "🔄 Template wiederhergestellt",
                f"**Name:** {name} | **Von:** {ctx.author}\n"
                f"Neue Rollen: {stats['created_roles']} | Neue Kategorien: {stats['created_cats']} | "
                f"Neue Channels: {stats['created_channels']} | Aktualisierte Channels: {stats['updated_channels']}",
                discord.Color.green(),
            )
            await msg.edit(content=(
                f"✅ Template **{name}** wiederhergestellt!\n"
                f"➕ {stats['created_roles']} Rollen | {stats['created_cats']} Kategorien | "
                f"{stats['created_channels']} neue Channels | {stats['updated_channels']} aktualisiert"
            ))
        except Exception as e:
            await msg.edit(content=f"❌ Fehler: {e}")

    @template_cmd.command(name="delete", aliases=["löschen"])
    @commands.has_permissions(administrator=True)
    async def template_delete(self, ctx, *, name: str):
        if delete_template(name):
            from utils import send_log
            await send_log(self.bot, "🗑️ Template gelöscht", f"**Name:** {name} | **Von:** {ctx.author}")
            await ctx.send(f"🗑️ Template **{name}** gelöscht.")
        else:
            await ctx.send(f"❌ Template **{name}** nicht gefunden.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TemplatesCog(bot))
