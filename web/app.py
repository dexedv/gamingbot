import sqlite3
import os
import time
import asyncio
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, current_app, session

app = Flask(__name__)
app.secret_key = os.getenv("WEB_SECRET", "changeme-set-WEB_SECRET-in-env")

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')
_bot_start_time = time.time()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        entered = request.form.get("password", "")
        valid_passwords = {os.getenv("WEB_PASSWORD", "admin"), os.getenv("WEB_PASSWORD_2", "")}
        valid_passwords.discard("")  # leere Einträge ignorieren
        if entered in valid_passwords:
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Falsches Passwort"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fmt_seconds(s):
    s = int(s or 0)
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m {sec}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def fmt_uptime(seconds):
    d = timedelta(seconds=int(seconds))
    parts = []
    if d.days:
        parts.append(f"{d.days}d")
    h, rem = divmod(d.seconds, 3600)
    m = rem // 60
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    return " ".join(parts) or "< 1m"


# ── Discord-Log ───────────────────────────────────────────────────────────────

def _discord_log(title: str, description: str = "", color: int = 0x5865f2):
    """Sendet eine Log-Nachricht asynchron in den Log-Kanal."""
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return
    try:
        import sys, os as _os
        sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..'))
        from utils import send_log
        import discord
        asyncio.run_coroutine_threadsafe(
            send_log(bot, title, description, discord.Color(color)),
            loop
        )
    except Exception:
        pass


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    db = get_db()
    stats = {
        "total_users":    db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_coins":    db.execute("SELECT SUM(coins) FROM users").fetchone()[0] or 0,
        "total_messages": db.execute("SELECT SUM(message_count) FROM users").fetchone()[0] or 0,
        "total_voice":    fmt_seconds(db.execute("SELECT SUM(voice_seconds) FROM users").fetchone()[0] or 0),
        "max_level":      db.execute("SELECT MAX(level) FROM users").fetchone()[0] or 0,
        "max_streak":     db.execute("SELECT MAX(streak) FROM users").fetchone()[0] or 0,
        "uptime":         fmt_uptime(time.time() - _bot_start_time),
    }
    top_coins  = db.execute("SELECT username, coins FROM users ORDER BY coins DESC LIMIT 5").fetchall()
    top_level  = db.execute("SELECT username, level, xp FROM users ORDER BY xp DESC LIMIT 5").fetchall()
    top_streak = db.execute("SELECT username, streak FROM users ORDER BY streak DESC LIMIT 5").fetchall()
    recent     = db.execute("SELECT username, coins, level, streak FROM users ORDER BY rowid DESC LIMIT 8").fetchall()
    db.close()
    return render_template("dashboard.html",
        stats=stats,
        top_coins=[dict(r) for r in top_coins],
        top_level=[dict(r) for r in top_level],
        top_streak=[dict(r) for r in top_streak],
        recent=[dict(r) for r in recent],
    )


# ── Leaderboards ──────────────────────────────────────────────────────────────

@app.route("/leaderboards")
@login_required
def leaderboards():
    db = get_db()
    coins   = [dict(r) for r in db.execute("SELECT username, coins FROM users ORDER BY coins DESC LIMIT 10").fetchall()]
    levels  = [dict(r) for r in db.execute("SELECT username, level, xp FROM users ORDER BY xp DESC LIMIT 10").fetchall()]
    streaks = [dict(r) for r in db.execute("SELECT username, streak, max_streak FROM users ORDER BY streak DESC LIMIT 10").fetchall()]
    chat    = [dict(r) for r in db.execute("SELECT username, message_count FROM users ORDER BY message_count DESC LIMIT 10").fetchall()]
    voice_r = db.execute("SELECT username, voice_seconds FROM users ORDER BY voice_seconds DESC LIMIT 10").fetchall()
    voice   = [{"username": r["username"], "voice_seconds": r["voice_seconds"], "voice_fmt": fmt_seconds(r["voice_seconds"])} for r in voice_r]
    db.close()
    return render_template("leaderboards.html",
        coins=coins, levels=levels, streaks=streaks, chat=chat, voice=voice)


# ── Users ─────────────────────────────────────────────────────────────────────

@app.route("/users")
@login_required
def users():
    db   = get_db()
    search = request.args.get("q", "").strip()
    if search:
        rows = db.execute(
            "SELECT * FROM users WHERE username LIKE ? ORDER BY coins DESC",
            (f"%{search}%",)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM users ORDER BY coins DESC").fetchall()
    users_list = []
    for r in rows:
        d = dict(r)
        d["voice_fmt"] = fmt_seconds(d.get("voice_seconds", 0))
        users_list.append(d)
    db.close()
    return render_template("users.html", users=users_list, search=search)


@app.route("/users/<int:user_id>/edit", methods=["POST"])
@login_required
def edit_user(user_id):
    coins  = request.form.get("coins",  type=int)
    streak = request.form.get("streak", type=int)
    level  = request.form.get("level",  type=int)
    xp     = request.form.get("xp",     type=int)
    db = get_db()
    changes = []
    if coins  is not None:
        db.execute("UPDATE users SET coins=?  WHERE user_id=?", (max(0, coins),  user_id))
        changes.append(f"Münzen: {max(0, coins)}")
    if streak is not None:
        db.execute("UPDATE users SET streak=? WHERE user_id=?", (max(0, streak), user_id))
        changes.append(f"Streak: {max(0, streak)}")
    if level  is not None:
        db.execute("UPDATE users SET level=?  WHERE user_id=?", (max(0, level),  user_id))
        changes.append(f"Level: {max(0, level)}")
    if xp     is not None:
        db.execute("UPDATE users SET xp=?     WHERE user_id=?", (max(0, xp),     user_id))
        changes.append(f"XP: {max(0, xp)}")
    db.commit()
    row = db.execute("SELECT username FROM users WHERE user_id=?", (user_id,)).fetchone()
    username = row["username"] if row else str(user_id)
    db.close()
    if changes:
        _discord_log("📝 Nutzer bearbeitet",
                     f"**Nutzer:** {username}\n" + "\n".join(changes))
    return redirect(url_for("users"))


# ── Settings ──────────────────────────────────────────────────────────────────

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '..', 'settings.json')

SETTINGS_DEFAULTS = {
    "nickname_updates":  True,
    "daily_xp":          30,
    "welcome_channel":   1019608622663209000,
    "msg_xp":            2,
    "msg_xp_per_min":    5,
    "voice_xp_per_30s":  1,
    "notify_channel":    1494057689435869485,
}

def load_settings():
    import json
    if os.path.exists(SETTINGS_PATH):
        data = json.load(open(SETTINGS_PATH, encoding="utf-8"))
        return {**SETTINGS_DEFAULTS, **data}
    return dict(SETTINGS_DEFAULTS)

def save_settings(s):
    import json
    json.dump(s, open(SETTINGS_PATH, "w", encoding="utf-8"), indent=2)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    s = load_settings()
    if request.method == "POST":
        s["nickname_updates"] = "nickname_updates" in request.form
        for key, lo, hi in [("daily_xp", 1, 500), ("msg_xp", 0, 100),
                             ("msg_xp_per_min", 1, 60), ("voice_xp_per_30s", 0, 50)]:
            val = request.form.get(key, type=int)
            if val is not None and lo <= val <= hi:
                s[key] = val
        notify_ch = request.form.get("notify_channel", "").strip()
        if notify_ch.isdigit():
            s["notify_channel"] = int(notify_ch)
        save_settings(s)
        _discord_log("⚙️ Einstellungen gespeichert",
                     f"Nachrichten-XP: {s.get('msg_xp')} | Max/Min: {s.get('msg_xp_per_min')} | "
                     f"Voice-XP/30s: {s.get('voice_xp_per_30s')} | "
                     f"Tages-XP: {s.get('daily_xp')} | "
                     f"Nickname-Updates: {s.get('nickname_updates')}")
        return redirect(url_for("settings"))
    return render_template("settings.html", settings=s)


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
@login_required
def api_stats():
    db = get_db()
    data = {
        "users":    db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "coins":    db.execute("SELECT SUM(coins) FROM users").fetchone()[0] or 0,
        "messages": db.execute("SELECT SUM(message_count) FROM users").fetchone()[0] or 0,
        "voice_s":  db.execute("SELECT SUM(voice_seconds) FROM users").fetchone()[0] or 0,
    }
    db.close()
    return jsonify(data)


# ── Cog Management ────────────────────────────────────────────────────────────

COGS_INFO = {
    "cogs.economy":   {"label": "Wirtschaft",       "icon": "💰", "desc": "Münzen, Daily, Bestenliste, Hilfe"},
    "cogs.levels":    {"label": "Level-System",      "icon": "⭐", "desc": "XP, Level-Up, Level-Rangliste"},
    "cogs.streak":    {"label": "Streak-System",     "icon": "🔥", "desc": "Tages-Streak, Meilensteine"},
    "cogs.ranks":     {"label": "Aktivitäts-Ränge",  "icon": "📊", "desc": "Chat- & Voice-Tracking, Ranglisten"},
    "cogs.tictactoe": {"label": "Tic-Tac-Toe",       "icon": "❌", "desc": "PvP Tic-Tac-Toe Spiel"},
    "cogs.slots":     {"label": "Spielautomat",       "icon": "🎰", "desc": "Slot-Machine mit Jackpot"},
    "cogs.blackjack": {"label": "Blackjack",          "icon": "🃏", "desc": "Blackjack gegen den Dealer"},
    "cogs.roulette":  {"label": "Roulette",           "icon": "🎡", "desc": "Roulette mit Zahlen & Farben"},
    "cogs.minigames": {"label": "Minispiele",         "icon": "🎲", "desc": "Coinflip, Würfeln, Higher or Lower"},
    "cogs.welcome":   {"label": "Willkommensnachrichten", "icon": "👋", "desc": "Begrüßt neue Mitglieder"},
}


@app.route("/api/cogs")
@login_required
def api_cogs():
    bot = current_app.config.get("BOT")
    if not bot:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    loaded = set(bot.extensions.keys())
    result = []
    for cog_name, info in COGS_INFO.items():
        result.append({
            "name":    cog_name,
            "label":   info["label"],
            "icon":    info["icon"],
            "desc":    info["desc"],
            "loaded":  cog_name in loaded,
        })
    return jsonify(result)


@app.route("/api/nickname-update", methods=["POST"])
@login_required
def trigger_nickname_update():
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    cog = bot.cogs.get("Streak")
    if not cog:
        return jsonify({"error": "Streak-Modul nicht geladen"}), 503
    try:
        future = asyncio.run_coroutine_threadsafe(cog.run_nickname_update(force=True), loop)
        future.result(timeout=60)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cogs/<path:cog_name>/toggle", methods=["POST"])
@login_required
def toggle_cog(cog_name):
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    if cog_name not in COGS_INFO:
        return jsonify({"error": "Unbekanntes Modul"}), 400

    try:
        if cog_name in bot.extensions:
            future = asyncio.run_coroutine_threadsafe(bot.unload_extension(cog_name), loop)
            future.result(timeout=10)
            loaded = False
        else:
            future = asyncio.run_coroutine_threadsafe(bot.load_extension(cog_name), loop)
            future.result(timeout=10)
            loaded = True
        status = "aktiviert" if loaded else "deaktiviert"
        _discord_log("🔧 Modul geändert",
                     f"**{COGS_INFO[cog_name]['label']}** (`{cog_name}`) wurde **{status}**")
        return jsonify({"name": cog_name, "loaded": loaded})
    except Exception as e:
        _discord_log("❌ Modul-Fehler",
                     f"**{cog_name}**\nFehler: {e}", 0xef4444)
        return jsonify({"error": str(e)}), 500


# ── Broadcast ─────────────────────────────────────────────────────────────────

@app.route("/broadcast")
@login_required
def broadcast():
    return render_template("broadcast.html")


@app.route("/api/channels")
@login_required
def api_channels():
    bot = current_app.config.get("BOT")
    if not bot:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    result = []
    for guild in bot.guilds:
        for channel in sorted(guild.text_channels, key=lambda c: (c.category.position if c.category else -1, c.position)):
            result.append({
                "id":       str(channel.id),
                "name":     channel.name,
                "guild":    guild.name,
                "category": channel.category.name if channel.category else "Ohne Kategorie",
            })
    return jsonify(result)


@app.route("/api/send-message", methods=["POST"])
@login_required
def api_send_message():
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    data       = request.get_json()
    channel_id = data.get("channel_id", "")
    message    = data.get("message", "").strip()
    if not channel_id or not message:
        return jsonify({"error": "Kanal und Nachricht erforderlich"}), 400
    if len(message) > 2000:
        return jsonify({"error": "Nachricht zu lang (max. 2000 Zeichen)"}), 400
    channel = bot.get_channel(int(channel_id))
    if not channel:
        return jsonify({"error": "Kanal nicht gefunden"}), 404
    try:
        future = asyncio.run_coroutine_threadsafe(channel.send(message), loop)
        future.result(timeout=10)
        preview = message[:150] + ("…" if len(message) > 150 else "")
        _discord_log("📨 Nachricht gesendet",
                     f"**Channel:** #{channel.name}\n**Nachricht:** {preview}")
        return jsonify({"ok": True, "channel": channel.name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Templates ─────────────────────────────────────────────────────────────────

def _tpl_module():
    import sys as _sys, os as _os
    root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), '..'))
    if root not in _sys.path:
        _sys.path.insert(0, root)
    from cogs import templates as m
    return m


@app.route("/templates")
@login_required
def templates():
    return render_template("templates.html")


@app.route("/api/templates")
@login_required
def api_templates_list():
    return jsonify(_tpl_module().list_templates())


@app.route("/api/templates/create", methods=["POST"])
@login_required
def api_templates_create():
    bot = current_app.config.get("BOT")
    if not bot or not bot.guilds:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        from datetime import datetime as _dt
        name = _dt.now().strftime("%Y-%m-%d_%H-%M")
    name = name.replace(" ", "_").replace("/", "-")[:50]
    try:
        meta = _tpl_module().save_template(name, bot.guilds[0], "Dashboard")
        _discord_log("📋 Template erstellt",
                     f"**Name:** {name} | **Via:** Dashboard\n"
                     f"Rollen: {meta['role_count']} | Kategorien: {meta['category_count']} | Channels: {meta['channel_count']}")
        return jsonify({"ok": True, "meta": meta})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/templates/<name>/restore", methods=["POST"])
@login_required
def api_templates_restore(name):
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop or not bot.guilds:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    m = _tpl_module()
    import os as _os
    if not _os.path.exists(_os.path.join(m.TEMPLATES_DIR, f"{name}.json")):
        return jsonify({"error": "Template nicht gefunden"}), 404
    cog = bot.cogs.get("Templates")
    if not cog:
        return jsonify({"error": "Templates-Modul nicht geladen"}), 503
    try:
        data  = m.load_template(name)
        guild = bot.guilds[0]
        future = asyncio.run_coroutine_threadsafe(cog.restore(guild, data), loop)
        stats  = future.result(timeout=120)
        _discord_log("🔄 Template wiederhergestellt",
                     f"**Name:** {name} | **Via:** Dashboard\n"
                     f"Neue Rollen: {stats['created_roles']} | Neue Kategorien: {stats['created_cats']} | "
                     f"Neue Channels: {stats['created_channels']} | Aktualisierte: {stats['updated_channels']}",
                     0x22c55e)
        return jsonify({"ok": True, "stats": stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/templates/<name>", methods=["GET", "DELETE"])
@login_required
def api_template_detail(name):
    m = _tpl_module()
    import os as _os
    path = _os.path.join(m.TEMPLATES_DIR, f"{name}.json")
    if not _os.path.exists(path):
        return jsonify({"error": "Template nicht gefunden"}), 404
    if request.method == "DELETE":
        m.delete_template(name)
        _discord_log("🗑️ Template gelöscht", f"**Name:** {name} | **Via:** Dashboard")
        return jsonify({"ok": True})
    return jsonify(m.load_template(name))


@app.route("/api/templates/<name>/download")
@login_required
def api_template_download(name):
    from flask import send_file
    m = _tpl_module()
    import os as _os
    path = _os.path.join(m.TEMPLATES_DIR, f"{name}.json")
    if not _os.path.exists(path):
        return "Nicht gefunden", 404
    return send_file(path, as_attachment=True, download_name=f"{name}.json", mimetype="application/json")


@app.route("/api/templates/upload", methods=["POST"])
@login_required
def api_template_upload():
    if "file" not in request.files:
        return jsonify({"error": "Keine Datei"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".json"):
        return jsonify({"error": "Nur JSON-Dateien erlaubt"}), 400
    try:
        import json as _json, os as _os
        data = _json.load(f)
        if "roles" not in data or "channels" not in data:
            return jsonify({"error": "Ungültiges Template-Format"}), 400
        name = data.get("meta", {}).get("name") or f.filename[:-5]
        name = name.replace(" ", "_").replace("/", "-")[:50]
        m = _tpl_module()
        _os.makedirs(m.TEMPLATES_DIR, exist_ok=True)
        with open(_os.path.join(m.TEMPLATES_DIR, f"{name}.json"), "w", encoding="utf-8") as fp:
            _json.dump(data, fp, indent=2, ensure_ascii=False)
        _discord_log("📤 Template importiert", f"**Name:** {name} | **Via:** Dashboard (Upload)")
        return jsonify({"ok": True, "name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
