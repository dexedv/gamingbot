import asyncio
import random
import discord
from discord.ext import commands

ADMIN_ID       = 243404681223733249
EVENT_DURATION = 30 * 60  # 30 Minuten in Sekunden
OWNER_ID       = 307210134856400908

TREASURE_CHANNELS = [
    494415444042584156,
    1494663152569417800,
    1494057689435869485,
    1494034948120645843,
    1494897669309726730,
    1494146941544825064,
    1494119689641525329,
    1494067153450831872,
    1494077718436773908,
    1019184912110211106,
]


class TreasureEventCog(commands.Cog, name="TreasureEvent"):
    def __init__(self, bot: commands.Bot):
        self.bot    = bot
        self.running = False
        self._task: asyncio.Task | None = None

    @commands.command(name="treasureevent")
    async def start_event(self, ctx: commands.Context, count: int = 10):
        """Startet das Treasure-Event — %treasureevent [anzahl]"""
        if ctx.author.id not in (OWNER_ID, ADMIN_ID):
            return
        if self.running:
            await ctx.send("⚠️ Ein Event läuft bereits. Stoppe es zuerst mit `%stopevent`.")
            return
        if count < 1 or count > 100:
            await ctx.send("❌ Anzahl muss zwischen 1 und 100 liegen.")
            return

        self.running = True
        self._task = asyncio.create_task(self._run_event(ctx.guild, count))

        interval_min = EVENT_DURATION / count / 60
        embed = discord.Embed(
            title="🎁 Treasure-Event gestartet!",
            description=(
                f"**{count}** Schatzkisten über **30 Minuten**\n"
                f"Ungefähr alle **{interval_min:.1f} Minuten** bekommt "
                f"<@{ADMIN_ID}> eine DM mit dem nächsten Spawn."
            ),
            color=discord.Color.from_rgb(255, 200, 0),
        )
        embed.set_footer(text="Stoppen: %stopevent")
        await ctx.send(embed=embed)

    @commands.command(name="stopevent")
    async def stop_event(self, ctx: commands.Context):
        """Stoppt das laufende Treasure-Event — %stopevent"""
        if ctx.author.id not in (OWNER_ID, ADMIN_ID):
            return
        if not self.running:
            await ctx.send("ℹ️ Kein Event aktiv.")
            return
        self.running = False
        if self._task:
            self._task.cancel()
        await ctx.send("⏹️ Treasure-Event gestoppt.")

    async def _run_event(self, guild: discord.Guild, count: int):
        try:
            admin = await self.bot.fetch_user(ADMIN_ID)
        except Exception:
            self.running = False
            return

        # Gleichmäßig verteilt + etwas Zufall
        base_interval = EVENT_DURATION / count

        # Startmeldung an Admin
        try:
            start_embed = discord.Embed(
                title="🎁 Treasure-Event — Du bist dran!",
                description=(
                    f"Du bekommst jetzt **{count}x** eine Nachricht mit dem Command "
                    f"den du im Server eingeben sollst.\n\n"
                    f"⏱️ Über **30 Minuten** verteilt · Ungefähr alle "
                    f"**{base_interval/60:.1f} Min**"
                ),
                color=discord.Color.from_rgb(255, 200, 0),
            )
            await admin.send(embed=start_embed)
        except Exception:
            pass

        for i in range(count):
            if not self.running:
                break

            # Warten (mit ±30% Zufall damit es natürlicher wirkt)
            wait = base_interval * random.uniform(0.7, 1.3)
            await asyncio.sleep(wait)

            if not self.running:
                break

            # Zufälligen Channel wählen
            ch_id   = random.choice(TREASURE_CHANNELS)

            # Entscheiden: /treasure oder /powerup
            use_powerup = (random.random() < 0.3)  # 30% Chance für Powerup

            if use_powerup:
                # Zufälligen Online-User wählen
                online = [
                    m for m in guild.members
                    if not m.bot and m.status != discord.Status.offline
                ]
                if online:
                    target = random.choice(online)
                    cmd_text = f"l.powerup {target.id} {ch_id}"
                    label    = f"⚡ Powerup für **{target.display_name}**"
                else:
                    # Kein Online-User → treasure statt powerup
                    cmd_text = "l.treasure"
                    label    = "🎁 Schatzkiste"
            else:
                cmd_text = "l.treasure"
                label    = "🎁 Schatzkiste"

            try:
                embed = discord.Embed(
                    title=label,
                    description=f"```\n{cmd_text}\n```",
                    color=discord.Color.from_rgb(255, 165, 0),
                )
                embed.add_field(name="📍 Channel", value=f"<#{ch_id}>", inline=False)
                embed.set_footer(text=f"Spawn {i+1}/{count} · Kopiere den Command und sende ihn im Server")
                await admin.send(embed=embed)
            except Exception:
                pass

        # Abschlussmeldung
        if self.running:
            self.running = False
            try:
                await admin.send(
                    embed=discord.Embed(
                        title="✅ Event abgeschlossen!",
                        description=f"Alle **{count}** Schatzkisten wurden gespawnt.",
                        color=discord.Color.green(),
                    )
                )
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TreasureEventCog(bot))
