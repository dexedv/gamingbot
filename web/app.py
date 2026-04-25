import sqlite3
import os
import time
import asyncio
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, current_app, session

app = Flask(__name__)
app.secret_key = os.getenv("WEB_SECRET", "changeme-set-WEB_SECRET-in-env")

from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gamingbot.db')
_bot_start_time = time.time()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


# ── Rollen & Rechte ───────────────────────────────────────────────────────────

# Numerisches Level je Rolle (höher = mehr Rechte)
ROLE_LEVEL = {
    "developer":       7,
    "owner":           6,
    "co-owner":        5,
    "admin":           4,
    "moderator":       3,
    "b-verifizierung": 2,
    "g-verifizierung": 2,
    "supporter":       2,
    "mediator":        1,
    "paten":           0,
}

VALID_ROLES = tuple(ROLE_LEVEL.keys())


def _parse_roles(raw) -> list:
    """Liest role-Wert aus DB — unterstützt alten String und neues JSON-Array."""
    import json as _j
    if not raw:
        return ["paten"]
    try:
        parsed = _j.loads(raw)
        if isinstance(parsed, list):
            return [r for r in parsed if r in VALID_ROLES] or ["paten"]
        if isinstance(parsed, str):
            return [parsed] if parsed in VALID_ROLES else ["paten"]
    except (ValueError, TypeError):
        pass
    return [raw] if raw in VALID_ROLES else ["paten"]


def _user_level(roles: list) -> int:
    """Gibt das höchste Level der Rollenliste zurück."""
    return max((ROLE_LEVEL.get(r, 0) for r in roles), default=0)

# ── Feature-basiertes Berechtigungssystem ────────────────────────────────────

FEATURES = {
    "nutzer":               {"label": "Nutzerliste",             "icon": "bi-people",          "desc": "Discord-Nutzer einsehen & Detailseiten aufrufen"},
    "knast_log":            {"label": "Knast-Log",               "icon": "bi-lock",           "desc": "Knast-Log & aktive Knast-Einträge lesen"},
    "kummerkasten":         {"label": "Kummerkasten",            "icon": "bi-envelope-heart",  "desc": "Kummerkasten-Statistiken einsehen"},
    "nutzer_verwalten":     {"label": "Nutzerverwaltung",        "icon": "bi-person-gear",     "desc": "Nutzer sperren, Coins & Level bearbeiten"},
    "umfragen":             {"label": "Umfragen",                "icon": "bi-ui-checks",       "desc": "Umfragen erstellen & schließen"},
    "verifizierung_boys":   {"label": "Boys-Verifizierung",      "icon": "bi-gender-male",     "desc": "Boys-Verifizierung konfigurieren"},
    "verifizierung_girls":  {"label": "Girls-Verifizierung",     "icon": "bi-gender-female",   "desc": "Girls-Verifizierung konfigurieren"},
    "broadcast":            {"label": "Nachrichten",             "icon": "bi-send",            "desc": "Broadcast & Nachrichten senden"},
    "willkommen":           {"label": "Willkommen-Editor",       "icon": "bi-door-open",       "desc": "Willkommensnachrichten bearbeiten & testen"},
    "cogs":                 {"label": "Module",                  "icon": "bi-boxes",           "desc": "Bot-Module aktivieren & deaktivieren"},
    "templates":            {"label": "Templates",               "icon": "bi-archive",         "desc": "Server-Templates erstellen & wiederherstellen"},
    "einstellungen":        {"label": "Einstellungen",           "icon": "bi-sliders",         "desc": "Bot-Einstellungen & XP-Konfiguration"},
    "web_nutzer":           {"label": "Web-Nutzer",              "icon": "bi-people-fill",     "desc": "Dashboard-Accounts verwalten"},
    "rolle_berechtigungen": {"label": "Rollen-Berechtigungen",   "icon": "bi-shield-lock",     "desc": "Zugriffsrechte der Rollen konfigurieren"},
    "server_log":           {"label": "Server-Log",              "icon": "bi-journal-text",    "desc": "Alle Server-Ereignisse einsehen"},
    "verified":             {"label": "Verifizierte Nutzer",     "icon": "bi-check-circle",    "desc": "Liste aller Nutzer die die Regeln akzeptiert haben"},
    "regelwerk_editor":     {"label": "Regelwerk-Editor",        "icon": "bi-pencil-square",   "desc": "Server-Regeln bearbeiten und in Discord posten"},
    "warns":                {"label": "Verwarnungen",             "icon": "bi-exclamation-triangle", "desc": "Verwarnungen aller Nutzer einsehen und verwalten"},
    "emoji_quiz":           {"label": "Emoji Quiz",               "icon": "bi-emoji-smile",          "desc": "Bananen-Leaderboard und Quiz-Statistiken einsehen"},
}

_REGELWERK_DEFAULTS = [
    {"title": "I. Respekt & Verhalten",
     "content": "➜ Behandle alle Mitglieder mit Respekt und Höflichkeit.\n➜ Beleidigungen, Diskriminierung, Hassrede oder Mobbing sind strikt verboten.\n➜ Provokationen, Trolling oder absichtliches Stören der Community werden nicht toleriert."},
    {"title": "II. Spam & Inhalte",
     "content": "➜ Kein Spam (z. B. wiederholte Nachrichten, unnötige Tags, Capslock-Missbrauch).\n➜ Keine Werbung ohne vorherige Erlaubnis des Teams.\n➜ Poste Inhalte nur in den dafür vorgesehenen Channels.\n➜ Vermeide Off-Topic in themenspezifischen Kanälen."},
    {"title": "III. NSFW & unangemessene Inhalte",
     "content": "➜ NSFW-, pornografische oder verstörende Inhalte sind verboten.\n➜ Keine gewaltverherrlichenden oder extremistischen Inhalte."},
    {"title": "IV. Datenschutz & Sicherheit",
     "content": "➜ Teile keine privaten Informationen (deine oder die anderer).\n➜ Scams oder Betrugsversuche führen zum sofortigen Bann.\n➜ Melde verdächtige Aktivitäten dem Team per Ticket."},
    {"title": "V. Umgang mit Moderation",
     "content": "➜ Folge den Anweisungen des Moderationsteams.\n➜ Das Ausnutzen von Lücken in den Regeln wird nicht toleriert.\n➜ Respektiere Entscheidungen – sie dienen dem Schutz der Community."},
    {"title": "VI. Sprache & Kommunikation",
     "content": "➜ Nutze eine angemessene Sprache (keine übermäßigen Beleidigungen oder vulgäre Ausdrucksweise).\n➜ Vermeide übermäßiges Ping/Tagging von Personen oder Rollen."},
    {"title": "VII. Voice-Chat Regeln",
     "content": "➜ Kein Schreien, Stören oder absichtliches Überlagern anderer.\n➜ Respektiere die Gespräche anderer Teilnehmer."},
    {"title": "VIII. Namen & Profile",
     "content": "➜ Keine beleidigenden, diskriminierenden oder unangemessenen Namen/Bilder/Bios.\n➜ Keine Nachahmung von Teammitgliedern oder anderen Nutzern."},
    {"title": "IX. Konsequenzen bei Regelverstößen",
     "content": "➜ Verwarnung.\n➜ Zeitlich begrenzter Mute/Kick.\n➜ Permanenter Bann.\n*(Die Strafe richtet sich nach Schwere des Verstoßes.)*"},
    {"title": "X. Sonstiges",
     "content": "➜ Das Team behält sich vor, Regeln jederzeit anzupassen.\n➜ Unwissenheit schützt nicht vor Strafe.\n➜ Mit dem Beitritt zum Server akzeptierst du diese Regeln."},
]


def _load_regelwerk() -> list[dict]:
    import json as _j
    try:
        db = get_db()
        row = db.execute("SELECT value FROM bot_settings WHERE key='regelwerk_rules'").fetchone()
        db.close()
        if row:
            data = _j.loads(row[0])
            if isinstance(data, list) and data:
                return data
    except Exception:
        pass
    return _REGELWERK_DEFAULTS


# Endpoint-Name → Feature
# Verifizierung-Routen sind NICHT hier — die prüfen ihr Feature selbst im Handler
FEATURE_ROUTES: dict[str, set] = {
    "nutzer":               {"users", "user_detail"},
    "knast_log":            {"knast_log"},
    "kummerkasten":         {"kummerkasten"},
    "nutzer_verwalten":     {"verwaltung", "edit_user", "api_user_knast"},
    "umfragen":             {"umfragen", "api_umfragen_erstellen", "api_umfragen_schliessen", "api_umfragen_aktiv"},
    "broadcast":            {"broadcast", "api_send_message", "api_channels"},
    "willkommen":           {"willkommen", "api_willkommen_test", "trigger_nickname_update"},
    "cogs":                 {"api_cogs", "toggle_cog"},
    "templates":            {"templates", "api_templates_list", "api_templates_create",
                             "api_templates_restore", "api_template_detail",
                             "api_template_download", "api_template_upload"},
    "einstellungen":        {"settings"},
    "web_nutzer":           {"web_users", "api_web_user_create", "api_web_user_edit", "api_web_user_delete"},
    "rolle_berechtigungen": {"role_permissions", "api_role_permissions_save"},
    "server_log":           {"server_log_page", "api_log_clear"},
    "verified":             {"verified_page", "api_verified_delete"},
    "regelwerk_editor":     {"regelwerk_editor_page", "api_regelwerk_save", "api_regelwerk_post"},
    "warns":                {"warns_page", "api_warns_clear"},
    "emoji_quiz":           {"emoji_quiz_page"},
}

# Reverse-Map: endpoint → feature (wird beim Import gebaut)
_ROUTE_FEATURE: dict[str, str] = {}
for _feat, _eps in FEATURE_ROUTES.items():
    for _ep in _eps:
        _ROUTE_FEATURE[_ep] = _feat

# Features die ausschließlich Developer aktivieren dürfen
DEV_ONLY_FEATURES = {"web_nutzer", "rolle_berechtigungen"}

DEFAULT_PERMISSIONS: dict[str, list] = {
    "developer":       list(FEATURES.keys()),
    "owner":           [f for f in FEATURES.keys() if f not in DEV_ONLY_FEATURES],
    "co-owner":        ["nutzer", "knast_log", "kummerkasten", "nutzer_verwalten", "umfragen",
                        "verifizierung_boys", "verifizierung_girls",
                        "broadcast", "willkommen", "cogs", "templates", "einstellungen", "server_log",
                        "verified", "regelwerk_editor", "warns", "emoji_quiz"],
    "admin":           ["nutzer", "knast_log", "kummerkasten", "nutzer_verwalten", "umfragen",
                        "verifizierung_boys", "verifizierung_girls", "broadcast", "willkommen",
                        "server_log", "verified", "regelwerk_editor", "warns", "emoji_quiz"],
    "moderator":       ["nutzer", "knast_log", "kummerkasten", "nutzer_verwalten", "umfragen",
                        "verifizierung_boys", "verifizierung_girls", "server_log", "verified", "warns", "emoji_quiz"],
    "b-verifizierung": ["verifizierung_boys"],
    "g-verifizierung": ["verifizierung_girls"],
    "supporter":       ["nutzer", "knast_log", "kummerkasten"],
    "mediator":        ["nutzer"],
    "paten":           [],
}

_perm_cache: dict = {}
_perm_cache_time: float = 0.0
PERM_CACHE_TTL = 30  # Sekunden


def _load_permissions() -> dict:
    """Lädt Rollen-Berechtigungen aus DB (mit 30s Cache)."""
    global _perm_cache, _perm_cache_time
    import json as _j
    now = time.time()
    if now - _perm_cache_time < PERM_CACHE_TTL and _perm_cache:
        return _perm_cache
    try:
        db = get_db()
        rows = db.execute("SELECT role, permissions FROM role_permissions").fetchall()
        db.close()
        stored = {}
        for row in rows:
            try:
                p = _j.loads(row["permissions"])
                if isinstance(p, list):
                    stored[row["role"]] = set(p)
            except Exception:
                pass
    except Exception:
        stored = {}
    result = {}
    for role in VALID_ROLES:
        result[role] = stored.get(role, set(DEFAULT_PERMISSIONS.get(role, [])))
    result["developer"] = set(FEATURES.keys())   # Developer immer alles
    _perm_cache = result
    _perm_cache_time = now
    return result


def _invalidate_perm_cache():
    global _perm_cache_time
    _perm_cache_time = 0.0


@app.before_request
def check_role():
    if request.endpoint in (None, "login", "logout", "static"):
        return
    if not session.get("logged_in"):
        return
    feature = _ROUTE_FEATURE.get(request.endpoint)
    if feature is None:
        return  # für alle eingeloggten Nutzer zugänglich
    roles = session.get("roles", ["paten"])
    perms = _load_permissions()
    for role in roles:
        if feature in perms.get(role, set()):
            return  # Zugriff gewährt
    return render_template("403.html", role=", ".join(roles)), 403


@app.context_processor
def inject_user_features():
    if not session.get("logged_in"):
        return {"user_features": set()}
    roles = session.get("roles", ["paten"])
    perms = _load_permissions()
    features: set = set()
    for role in roles:
        features |= perms.get(role, set())
    return {"user_features": features}


def _ensure_permissions():
    """Erstellt role_permissions-Tabelle und befüllt fehlende Rollen einmalig mit Defaults.
    Bestehende Einträge werden NIE verändert — nur Developer bekommt immer alle Features."""
    import json as _j
    try:
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role        TEXT PRIMARY KEY,
                permissions TEXT NOT NULL DEFAULT '[]'
            )
        """)
        db.commit()

        # Einmalige Migration: altes 'verifizierung'-Feature → boys/girls aufteilen
        for row in db.execute("SELECT role, permissions FROM role_permissions").fetchall():
            try:
                perms = set(_j.loads(row["permissions"]))
            except Exception:
                continue
            if "verifizierung" not in perms:
                continue
            perms.discard("verifizierung")
            if row["role"] == "b-verifizierung":
                perms.add("verifizierung_boys")
            elif row["role"] == "g-verifizierung":
                perms.add("verifizierung_girls")
            else:
                perms.add("verifizierung_boys")
                perms.add("verifizierung_girls")
            db.execute("UPDATE role_permissions SET permissions=? WHERE role=?",
                       (_j.dumps(sorted(perms)), row["role"]))
        db.commit()

        # Fehlende Rollen einmalig mit Defaults befüllen (INSERT OR IGNORE = nie überschreiben)
        for role in VALID_ROLES:
            default_p = list(FEATURES.keys()) if role == "developer" else DEFAULT_PERMISSIONS.get(role, [])
            db.execute(
                "INSERT OR IGNORE INTO role_permissions (role, permissions) VALUES (?,?)",
                (role, _j.dumps(sorted(default_p)))
            )
        db.commit()

        # Developer bekommt immer alle Features (einzige Auto-Anpassung)
        all_features = _j.dumps(sorted(FEATURES.keys()))
        db.execute("UPDATE role_permissions SET permissions=? WHERE role='developer'", (all_features,))
        db.commit()

        db.close()
        _invalidate_perm_cache()
    except Exception:
        pass


def _ensure_admin_user():
    """Erstellt den ersten Admin-Account wenn web_users leer ist und migriert alte Einzel-Rollen."""
    import json as _j
    try:
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS web_users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT '["paten"]',
                created_at    TEXT    DEFAULT (datetime('now'))
            )
        """)
        db.commit()
        # Migration: Einzel-String → JSON-Array
        for row in db.execute("SELECT id, role FROM web_users").fetchall():
            raw = row["role"]
            try:
                parsed = _j.loads(raw)
                if not isinstance(parsed, list):
                    db.execute("UPDATE web_users SET role=? WHERE id=?",
                               (_j.dumps([str(parsed)]), row["id"]))
            except (ValueError, TypeError):
                db.execute("UPDATE web_users SET role=? WHERE id=?",
                           (_j.dumps([raw] if raw else ["paten"]), row["id"]))
        db.commit()
        if db.execute("SELECT COUNT(*) FROM web_users").fetchone()[0] == 0:
            uname = os.getenv("WEB_ADMIN_USER", "admin")
            pw    = os.getenv("WEB_PASSWORD", "admin")
            db.execute(
                "INSERT INTO web_users (username, password_hash, role) VALUES (?,?,?)",
                (uname, generate_password_hash(pw), _j.dumps(["developer"]))
            )
            db.commit()
        db.close()
        _ensure_permissions()
    except Exception:
        pass


@app.route("/login", methods=["GET", "POST"])
def login():
    _ensure_admin_user()
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        row = db.execute(
            "SELECT password_hash, role FROM web_users WHERE username=?", (username,)
        ).fetchone()
        db.close()
        if row and check_password_hash(row["password_hash"], password):
            session["logged_in"] = True
            session["username"]  = username
            session["roles"]     = _parse_roles(row["role"])
            return redirect(request.args.get("next") or url_for("dashboard"))
        error = "Benutzername oder Passwort falsch"
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
        "total_bananen":  db.execute("SELECT SUM(aepfel) FROM users").fetchone()[0] or 0,
        "total_warns":    db.execute("SELECT COALESCE(SUM(amount),0) FROM warns").fetchone()[0] or 0,
        "knast_active":   db.execute("SELECT COUNT(*) FROM knast WHERE released_at IS NULL").fetchone()[0] or 0,
        "uptime":         fmt_uptime(time.time() - _bot_start_time),
    }
    top_coins   = db.execute("SELECT username, coins FROM users ORDER BY coins DESC LIMIT 5").fetchall()
    top_level   = db.execute("SELECT username, level, xp FROM users ORDER BY xp DESC LIMIT 5").fetchall()
    top_streak  = db.execute("SELECT username, streak FROM users ORDER BY streak DESC LIMIT 5").fetchall()
    top_bananen = db.execute("SELECT username, aepfel FROM users ORDER BY aepfel DESC LIMIT 5").fetchall()
    recent      = db.execute("SELECT username, coins, level, streak FROM users ORDER BY rowid DESC LIMIT 8").fetchall()
    db.close()
    return render_template("dashboard.html",
        stats=stats,
        top_coins=[dict(r) for r in top_coins],
        top_level=[dict(r) for r in top_level],
        top_streak=[dict(r) for r in top_streak],
        top_bananen=[dict(r) for r in top_bananen],
        recent=[dict(r) for r in recent],
    )


# ── Leaderboards ──────────────────────────────────────────────────────────────

@app.route("/leaderboards")
@login_required
def leaderboards():
    db = get_db()
    rows = db.execute(
        "SELECT username, coins, level, xp, streak, max_streak, message_count, voice_seconds "
        "FROM users ORDER BY coins DESC"
    ).fetchall()
    users = []
    for r in rows:
        u = dict(r)
        u["voice_fmt"] = fmt_seconds(u.get("voice_seconds") or 0)
        users.append(u)
    db.close()
    return render_template("leaderboards.html", users=users)


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


@app.route("/users/<int:user_id>")
@login_required
def user_detail(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        db.close()
        return redirect(url_for("users"))
    u = dict(row)
    u["voice_fmt"] = fmt_seconds(u.get("voice_seconds") or 0)
    xp    = u.get("xp") or 0
    level = u.get("level") or 0
    xp_curr = xp - level * level * 50
    xp_need = (level + 1) * (level + 1) * 50 - level * level * 50
    xp_pct  = min(100, int(xp_curr / xp_need * 100)) if xp_need > 0 else 100
    # Knast-Status
    knast_row = db.execute(
        "SELECT reason, jailed_at FROM knast WHERE user_id=?", (user_id,)
    ).fetchone()
    knast_info = dict(knast_row) if knast_row else None
    # Letzter Knast-Log-Eintrag
    knast_log_rows = db.execute(
        "SELECT action, by_name, reason, created_at FROM knast_log "
        "WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (user_id,)
    ).fetchall()
    db.close()
    return render_template("user_detail.html", u=u,
                           xp_curr=xp_curr, xp_need=xp_need, xp_pct=xp_pct,
                           knast_info=knast_info,
                           knast_log=[dict(r) for r in knast_log_rows])


@app.route("/api/users/<int:user_id>/knast", methods=["POST"])
@login_required
def api_user_knast(user_id):
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503

    data   = request.get_json() or {}
    action = data.get("action")       # "jail" | "release"
    reason = data.get("reason", "Via Dashboard").strip() or "Via Dashboard"

    if action not in ("jail", "release"):
        return jsonify({"error": "Ungültige Aktion"}), 400

    if not bot.guilds:
        return jsonify({"error": "Bot ist auf keinem Server"}), 503
    guild  = bot.guilds[0]
    member = guild.get_member(user_id)
    if not member:
        return jsonify({"error": "Nutzer nicht auf dem Server gefunden (evtl. offline/nicht gecacht)"}), 404

    cog = bot.cogs.get("Knast")
    if not cog:
        return jsonify({"error": "Knast-Modul nicht geladen"}), 503

    async def _run():
        if action == "jail":
            return await cog.jail_member(member, reason, "Dashboard", 0)
        else:
            return await cog.release_member(member, reason, "Dashboard", 0)

    try:
        result = asyncio.run_coroutine_threadsafe(_run(), loop).result(timeout=60)
        if result.get("error"):
            return jsonify({"error": result["error"]}), 400
        action_label = "eingesperrt" if action == "jail" else "entlassen"
        _discord_log(
            "🔒 Knast via Dashboard" if action == "jail" else "🔓 Entlassung via Dashboard",
            f"👤  **Nutzer:** {member} (`{member.id}`)\n"
            f"📝  **Grund:** {reason}\n"
            f"🌐  **Via:** Dashboard"
        )
        return jsonify({"ok": True, "label": action_label})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
                     f"👤  **Nutzer:** {username}\n"
                     + "\n".join(f"✏️  {c}" for c in changes))
    return redirect(url_for("users"))


# ── Settings ──────────────────────────────────────────────────────────────────

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '..', 'settings.json')

SETTINGS_DEFAULTS = {
    "nickname_updates":       True,
    "daily_xp":               30,
    "welcome_channel":        1019608622663209000,
    "msg_xp":                 2,
    "msg_xp_per_min":         5,
    "voice_xp_per_30s":       1,
    "notify_channel":         1494057689435869485,
    "welcome_enabled":        True,
    "welcome_title":          "👋 Willkommen auf {guild}!",
    "welcome_description":    "Schön dass du da bist, {mention}! 🎉\nDu bist unser **{count}. Mitglied** — herzlich willkommen!",
    "welcome_color":          "#5865f2",
    "welcome_rules_channel":  1019184912110211103,
    "welcome_rules_text":     "Lies unsere Regeln durch bevor du loslegst!",
    "welcome_roles_channel":  1019594993226219610,
    "welcome_roles_text":     "Such dir deine Rollen aus!",
    "welcome_paten_channel":  1494054503647805562,
    "welcome_paten_text":     "Neu hier? Wir haben ein **Paten-System**!\nEin erfahrenes Mitglied begleitet dich.",
    "welcome_footer":         "{guild} • Viel Spaß!",
    "welcome_show_banner":    True,
    "gif_limit_enabled":          False,
    "gif_limit_per_minute":       3,
    "gif_limit_warn":             True,
    "gif_limit_delete":           True,
    "gif_limit_bypass_roles":     [],
    "gif_limit_exempt_channels":  [],
}

def load_settings():
    import json
    try:
        db = get_db()
        rows = db.execute("SELECT key, value FROM bot_settings").fetchall()
        db.close()
        if rows:
            stored = {}
            for r in rows:
                try:
                    stored[r[0]] = json.loads(r[1])
                except Exception:
                    stored[r[0]] = r[1]
            return {**SETTINGS_DEFAULTS, **stored}
    except Exception:
        pass
    # Fallback: settings.json (Migration beim ersten Aufruf)
    if os.path.exists(SETTINGS_PATH):
        try:
            data = json.load(open(SETTINGS_PATH, encoding="utf-8"))
            merged = {**SETTINGS_DEFAULTS, **data}
            save_settings(merged)
            return merged
        except Exception:
            pass
    return dict(SETTINGS_DEFAULTS)

def save_settings(s):
    import json
    try:
        db = get_db()
        for key, val in s.items():
            db.execute(
                "INSERT INTO bot_settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(val))
            )
        db.commit()
        db.close()
    except Exception:
        pass

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
        # GIF-Limit
        s["gif_limit_enabled"] = "gif_limit_enabled" in request.form
        s["gif_limit_warn"]    = "gif_limit_warn"    in request.form
        s["gif_limit_delete"]  = "gif_limit_delete"  in request.form
        gif_per_min = request.form.get("gif_limit_per_minute", type=int)
        if gif_per_min is not None and 1 <= gif_per_min <= 60:
            s["gif_limit_per_minute"] = gif_per_min
        # Bypass-Rollen: kommagetrennte IDs
        bypass_raw = request.form.get("gif_limit_bypass_roles", "").strip()
        s["gif_limit_bypass_roles"] = [
            int(x.strip()) for x in bypass_raw.split(",") if x.strip().isdigit()
        ]
        # Ausgenommene Kanäle: kommagetrennte IDs
        exempt_raw = request.form.get("gif_limit_exempt_channels", "").strip()
        s["gif_limit_exempt_channels"] = [
            int(x.strip()) for x in exempt_raw.split(",") if x.strip().isdigit()
        ]
        save_settings(s)
        _discord_log("⚙️ Einstellungen gespeichert",
                     f"💬  **Nachrichten-XP:** {s.get('msg_xp')} | Max: {s.get('msg_xp_per_min')}/min\n"
                     f"🎙️  **Voice-XP/30s:** {s.get('voice_xp_per_30s')}\n"
                     f"🎁  **Tages-XP:** {s.get('daily_xp')}\n"
                     f"🏷️  **Nickname-Updates:** {'✅ An' if s.get('nickname_updates') else '⛔ Aus'}\n"
                     f"🎞️  **GIF-Limit:** {'✅ An' if s.get('gif_limit_enabled') else '⛔ Aus'}"
                     + (f" · max {s.get('gif_limit_per_minute')}/min" if s.get('gif_limit_enabled') else ""))
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
    "cogs.welcome":    {"label": "Willkommensnachrichten", "icon": "👋", "desc": "Begrüßt neue Mitglieder"},
    "cogs.gif_limit":  {"label": "GIF-Limit",             "icon": "🎞️", "desc": "GIFs pro Minute pro Nutzer begrenzen"},
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
                     f"📦  **Modul:** {COGS_INFO[cog_name]['label']}\n"
                     f"📁  **Datei:** `{cog_name}`\n"
                     f"🔘  **Status:** {'✅ Aktiviert' if loaded else '⛔ Deaktiviert'}")
        return jsonify({"name": cog_name, "loaded": loaded})
    except Exception as e:
        _discord_log("❌ Modul-Fehler",
                     f"📦  **Modul:** `{cog_name}`\n"
                     f"⚠️  **Fehler:** {e}", 0xef4444)
        return jsonify({"error": str(e)}), 500


# ── Benutzerverwaltung ────────────────────────────────────────────────────────

@app.route("/verwaltung")
@login_required
def verwaltung():
    db = get_db()
    search = request.args.get("q", "").strip()
    if search:
        rows = db.execute(
            "SELECT * FROM users WHERE username LIKE ? OR user_id LIKE ? ORDER BY username",
            (f"%{search}%", f"%{search}%")
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM users ORDER BY username").fetchall()
    # Knast-Status für alle Nutzer laden
    jailed = {
        r["user_id"]: r
        for r in db.execute("SELECT user_id, reason, jailed_at FROM knast").fetchall()
    }
    db.close()
    users_list = []
    for r in rows:
        u = dict(r)
        u["voice_fmt"]    = fmt_seconds(u.get("voice_seconds", 0))
        knast             = jailed.get(u["user_id"])
        u["is_jailed"]    = knast is not None
        u["knast_reason"] = dict(knast)["reason"] if knast else None
        users_list.append(u)
    return render_template("verwaltung.html", users=users_list, search=search)


# ── Befehle ───────────────────────────────────────────────────────────────────

@app.route("/befehle")
@login_required
def befehle():
    return render_template("befehle.html")


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
                     f"📢  **Kanal:** #{channel.name}\n"
                     f"💬  **Inhalt:** {preview}")
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
    m = _tpl_module()
    wait = m._cooldown_remaining()
    if wait > 0:
        h, mins = divmod(wait // 60, 60)
        return jsonify({"error": f"Templates können nur alle 12h erstellt werden. Noch {h}h {mins}m warten."}), 429
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        from datetime import datetime as _dt
        name = _dt.now().strftime("%Y-%m-%d_%H-%M")
    name = name.replace(" ", "_").replace("/", "-")[:50]
    try:
        meta = _tpl_module().save_template(name, bot.guilds[0], "Dashboard")
        _discord_log("📋 Template erstellt",
                     f"📄  **Name:** `{name}`\n"
                     f"🎭  **Rollen:** {meta['role_count']}  |  📂  **Kategorien:** {meta['category_count']}  |  #  **Channels:** {meta['channel_count']}\n"
                     f"🌐  **Via:** Dashboard")
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
                     f"📄  **Name:** `{name}`\n"
                     f"🎭  **Neue Rollen:** {stats['created_roles']}  |  📂  **Neue Kategorien:** {stats['created_cats']}\n"
                     f"#  **Neue Channels:** {stats['created_channels']}  |  🔁  **Aktualisiert:** {stats['updated_channels']}\n"
                     f"🌐  **Via:** Dashboard",
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
        _discord_log("🗑️ Template gelöscht",
                     f"📄  **Name:** `{name}`\n"
                     f"🌐  **Via:** Dashboard")
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


# ── Willkommen-Editor ─────────────────────────────────────────────────────────

@app.route("/willkommen", methods=["GET", "POST"])
@login_required
def willkommen():
    s = load_settings()
    if request.method == "POST":
        s["welcome_enabled"]    = "welcome_enabled" in request.form
        s["welcome_show_banner"] = "welcome_show_banner" in request.form
        for key in ["welcome_title", "welcome_description", "welcome_color",
                    "welcome_footer", "welcome_rules_text", "welcome_roles_text", "welcome_paten_text"]:
            val = request.form.get(key, "").strip()
            if val:
                s[key] = val
        for key in ["welcome_channel", "welcome_rules_channel",
                    "welcome_roles_channel", "welcome_paten_channel"]:
            val = request.form.get(key, "").strip()
            if val.isdigit():
                s[key] = int(val)
        save_settings(s)
        _discord_log("👋 Willkommens-Nachricht bearbeitet",
                     f"📝  **Titel:** {s['welcome_title'][:60]}\n"
                     f"📢  **Kanal:** <#{s['welcome_channel']}>\n"
                     f"🎨  **Farbe:** `{s.get('welcome_color', '#5865f2')}`  |  "
                     f"🖼️  **Banner:** {'✅' if s.get('welcome_show_banner') else '⛔'}")
        return redirect(url_for("willkommen"))
    return render_template("willkommen.html", s=s)


@app.route("/api/willkommen/test", methods=["POST"])
@login_required
def api_willkommen_test():
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    s = load_settings()
    channel_id = int(s.get("welcome_channel", 0))
    channel = bot.get_channel(channel_id)
    if not channel:
        return jsonify({"error": f"Kanal {channel_id} nicht gefunden"}), 404

    async def _send():
        import discord as _d
        def fmt(text):
            return str(text).replace("{mention}", "@Dashboard-Test") \
                            .replace("{guild}", channel.guild.name) \
                            .replace("{count}", str(channel.guild.member_count)) \
                            .replace("{username}", "Testnutzer")
        try:
            r, g, b = [int(s["welcome_color"].lstrip('#')[i:i+2], 16) for i in (0,2,4)]
            color = _d.Color.from_rgb(r, g, b)
        except Exception:
            color = _d.Color.blurple()
        embed = _d.Embed(
            title=fmt(s["welcome_title"]),
            description=fmt(s["welcome_description"]),
            color=color,
        )
        if s.get("welcome_show_banner") and channel.guild.banner:
            embed.set_image(url=channel.guild.banner.url)
        embed.add_field(
            name="📜  Regeln",
            value=f"{fmt(s.get('welcome_rules_text', 'Lies unsere Regeln durch bevor du loslegst!'))}\n<#{int(s['welcome_rules_channel'])}>",
            inline=True,
        )
        embed.add_field(
            name="🎭  Rollen",
            value=f"{fmt(s.get('welcome_roles_text', 'Such dir deine Rollen aus!'))}\n<#{int(s['welcome_roles_channel'])}>",
            inline=True,
        )
        embed.add_field(
            name="🤝  Paten-System",
            value=f"{fmt(s.get('welcome_paten_text', 'Neu hier? Wir haben ein **Paten-System**!'))}\nTicket öffnen: <#{int(s['welcome_paten_channel'])}>",
            inline=False,
        )
        embed.set_footer(
            text=fmt(s["welcome_footer"]),
            icon_url=channel.guild.icon.url if channel.guild.icon else None,
        )
        embed.set_author(name="⚠️ TEST-Nachricht vom Dashboard")
        await channel.send(embed=embed)

    try:
        asyncio.run_coroutine_threadsafe(_send(), loop).result(timeout=10)
        return jsonify({"ok": True, "channel": channel.name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Verifizierung ─────────────────────────────────────────────────────────────

VERIFY_DEFAULTS = {
    "boys": {
        "verify_title":        "✅ Boys-Verifizierung",
        "verify_description":  "Klicke auf den Button unten, um ein Ticket zu öffnen.\nEin Moderator wird dich dann verifizieren.\n\n🎫 **Ticket erstellen** → Button drücken",
        "ticket_title":        "🎫 Boys-Verifizierungs-Ticket",
        "ticket_description":  "Willkommen {mention}!\n\nEin Moderator wird sich in Kürze um dein Ticket kümmern.\nSchreibe hier dein Anliegen oder warte auf weitere Anweisungen.\n\nZum Schließen des Tickets den Button unten nutzen.",
        "verify_channel":      1494483085687914657,
        "ticket_category":     1494482692039774331,
        "transcript_channel":  0,
    },
    "girls": {
        "verify_title":        "✅ Girls-Verifizierung",
        "verify_description":  "Klicke auf den Button unten, um ein Ticket zu öffnen.\nEin Moderator wird dich dann verifizieren.\n\n🎫 **Ticket erstellen** → Button drücken",
        "ticket_title":        "🎫 Girls-Verifizierungs-Ticket",
        "ticket_description":  "Willkommen {mention}!\n\nEin Moderator wird sich in Kürze um dein Ticket kümmern.\nSchreibe hier dein Anliegen oder warte auf weitere Anweisungen.\n\nZum Schließen des Tickets den Button unten nutzen.",
        "verify_channel":      0,
        "ticket_category":     0,
        "transcript_channel":  0,
    },
}


@app.route("/verifizierung/<prefix>", methods=["GET", "POST"])
@login_required
def verifizierung(prefix):
    import json as _json
    if prefix not in ("boys", "girls"):
        return redirect(url_for("verifizierung", prefix="boys"))
    required = f"verifizierung_{prefix}"
    _vroles = session.get("roles", ["paten"])
    _perms  = _load_permissions()
    if not any(required in _perms.get(r, set()) for r in _vroles):
        return render_template("403.html", role=", ".join(_vroles)), 403

    db = get_db()
    defs = VERIFY_DEFAULTS[prefix]

    def _get_db(key, default=""):
        row = db.execute("SELECT value FROM bot_settings WHERE key=?", (f"{prefix}_{key}",)).fetchone()
        return _json.loads(row[0]) if row else default

    def _set_db(key, val):
        db.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (f"{prefix}_{key}", _json.dumps(val))
        )

    if request.method == "POST":
        changed = []
        for key, lbl in [
            ("verify_title",        "Verify-Titel"),
            ("verify_description",  "Verify-Text"),
            ("ticket_title",        "Ticket-Titel"),
            ("ticket_description",  "Ticket-Text"),
        ]:
            val = request.form.get(key, "").strip()
            if key in ("verify_description", "ticket_description"):
                val = val.replace("\\n", "\n")
            if val:
                _set_db(key, val)
                changed.append(lbl)
        ch = request.form.get("verify_channel", "").strip()
        if ch.isdigit():
            _set_db("verify_channel", int(ch))
        cat = request.form.get("ticket_category", "").strip()
        if cat.isdigit():
            _set_db("ticket_category", int(cat))
        trc = request.form.get("transcript_channel", "").strip()
        if trc.isdigit():
            _set_db("transcript_channel", int(trc))
        db.commit()
        db.close()
        if changed:
            plabel = "Boys" if prefix == "boys" else "Girls"
            _discord_log(f"🎫 {plabel}-Verifizierung bearbeitet",
                         f"✏️  **Geändert:** {', '.join(changed)}\n🌐  **Via:** Dashboard")
        return redirect(url_for("verifizierung", prefix=prefix))

    verify_title         = _get_db("verify_title",       defs["verify_title"])
    verify_description   = _get_db("verify_description", defs["verify_description"])
    ticket_title         = _get_db("ticket_title",       defs["ticket_title"])
    ticket_description   = _get_db("ticket_description", defs["ticket_description"])
    verify_channel_id    = _get_db("verify_channel",     defs["verify_channel"])
    ticket_category_id   = _get_db("ticket_category",    defs["ticket_category"])
    transcript_channel_id = _get_db("transcript_channel", defs["transcript_channel"])
    mod_role_ids         = _get_db("mod_roles",          [])
    db.close()

    bot = current_app.config.get("BOT")
    mod_roles  = []
    channels   = []
    categories = []
    if bot and bot.guilds:
        guild = bot.guilds[0]
        for rid in mod_role_ids:
            role = guild.get_role(int(rid))
            mod_roles.append({"id": rid, "name": role.name if role else f"ID {rid}"})
        for ch in sorted(guild.text_channels, key=lambda c: (c.category.position if c.category else -1, c.position)):
            channels.append({
                "id": str(ch.id),
                "name": ch.name,
                "category": ch.category.name if ch.category else "Ohne Kategorie",
            })
        for cat in sorted(guild.categories, key=lambda c: c.position):
            categories.append({"id": str(cat.id), "name": cat.name})

    return render_template("verify_system.html",
        prefix=prefix,
        verify_title=verify_title,
        verify_description=verify_description,
        ticket_title=ticket_title,
        ticket_description=ticket_description,
        verify_channel_id=str(verify_channel_id),
        ticket_category_id=str(ticket_category_id),
        transcript_channel_id=str(transcript_channel_id),
        mod_roles=mod_roles,
        channels=channels,
        categories=categories,
    )


@app.route("/api/verifizierung/<prefix>/setup", methods=["POST"])
@login_required
def api_verifizierung_setup(prefix):
    import json as _json
    if prefix not in ("boys", "girls"):
        return jsonify({"error": "Ungültiger Prefix"}), 400
    required = f"verifizierung_{prefix}"
    _vroles  = session.get("roles", ["paten"])
    _perms   = _load_permissions()
    if not any(required in _perms.get(r, set()) for r in _vroles):
        return jsonify({"error": f"Kein Zugriff auf {prefix.capitalize()}-Verifizierung"}), 403
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503

    defs = VERIFY_DEFAULTS[prefix]

    async def _send():
        import discord as _d
        import sqlite3 as _sq, os as _os, sys as _sys
        db_path = _os.path.join(_os.path.dirname(__file__), '..', 'data', 'gamingbot.db')
        conn = _sq.connect(db_path)

        def _g(key, default):
            row = conn.execute("SELECT value FROM bot_settings WHERE key=?", (f"{prefix}_{key}",)).fetchone()
            return _json.loads(row[0]) if row else default

        title  = _g("verify_title",       defs["verify_title"])
        desc   = _g("verify_description", defs["verify_description"])
        ch_id  = _g("verify_channel",     defs["verify_channel"])
        conn.close()

        channel = bot.get_channel(int(ch_id))
        if not channel:
            raise ValueError(f"Kanal {ch_id} nicht gefunden")

        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..'))
        if prefix == "boys":
            from cogs.verifizierung import BoysVerifyView as VView
            color = _d.Color.from_rgb(88, 101, 242)
        else:
            from cogs.verifizierung import GirlsVerifyView as VView
            color = _d.Color.from_rgb(236, 72, 153)

        plabel = "Boys" if prefix == "boys" else "Girls"
        embed = _d.Embed(title=title, description=desc, color=color)
        embed.set_footer(text=f"Pink Horizoon Bot · {plabel}-Verifizierung")
        await channel.send(embed=embed, view=VView())

    try:
        asyncio.run_coroutine_threadsafe(_send(), loop).result(timeout=15)
        plabel = "Boys" if prefix == "boys" else "Girls"
        _discord_log(f"✅ {plabel}-Verifizierungs-Nachricht gesendet", "📢  **Via:** Dashboard")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/verifizierung/<prefix>/modrole", methods=["POST"])
@login_required
def api_verifizierung_modrole(prefix):
    import json as _json
    if prefix not in ("boys", "girls"):
        return jsonify({"error": "Ungültiger Prefix"}), 400
    required = f"verifizierung_{prefix}"
    _vroles  = session.get("roles", ["paten"])
    _perms   = _load_permissions()
    if not any(required in _perms.get(r, set()) for r in _vroles):
        return jsonify({"error": f"Kein Zugriff auf {prefix.capitalize()}-Verifizierung"}), 403
    data    = request.get_json() or {}
    role_id = data.get("role_id")
    action  = data.get("action", "toggle")
    if not role_id:
        return jsonify({"error": "role_id fehlt"}), 400
    role_id = int(role_id)
    db_key  = f"{prefix}_mod_roles"

    db    = get_db()
    row   = db.execute("SELECT value FROM bot_settings WHERE key=?", (db_key,)).fetchone()
    roles = _json.loads(row[0]) if row else []

    if action == "remove" or (action == "toggle" and role_id in roles):
        roles = [r for r in roles if r != role_id]
        lbl = "entfernt"
    else:
        if role_id not in roles:
            roles.append(role_id)
        lbl = "hinzugefügt"

    db.execute(
        "INSERT INTO bot_settings (key,value) VALUES (?,?)"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (db_key, _json.dumps(roles))
    )
    db.commit()
    db.close()

    bot = current_app.config.get("BOT")
    role_name = f"ID {role_id}"
    if bot and bot.guilds:
        role = bot.guilds[0].get_role(role_id)
        if role:
            role_name = role.name
    plabel = "Boys" if prefix == "boys" else "Girls"
    _discord_log(f"🎫 {plabel}-Mod-Rolle geändert",
                 f"🎭  **Rolle:** {role_name}\n🔘  **Aktion:** {lbl}\n🌐  **Via:** Dashboard")
    return jsonify({"ok": True, "roles": roles, "label": lbl})


# ── Kummerkasten ───────────────────────────────────────────────────────────────

@app.route("/kummerkasten")
@login_required
def kummerkasten():
    db = get_db()
    try:
        total = db.execute("SELECT COUNT(*) FROM kummerkasten_log").fetchone()[0]
        today = db.execute(
            "SELECT COUNT(*) FROM kummerkasten_log WHERE date(created_at)=date('now')"
        ).fetchone()[0]
        week = db.execute(
            "SELECT COUNT(*) FROM kummerkasten_log WHERE created_at >= datetime('now','-7 days')"
        ).fetchone()[0]
        daily = db.execute(
            "SELECT date(created_at) as day, COUNT(*) as cnt "
            "FROM kummerkasten_log WHERE created_at >= datetime('now','-30 days') "
            "GROUP BY day ORDER BY day"
        ).fetchall()
        daily = [dict(r) for r in daily]
    except Exception:
        total, today, week, daily = 0, 0, 0, []
    db.close()
    return render_template("kummerkasten.html",
        total=total, today=today, week=week, daily=daily)


# ── Knast-Log ────────────────────────────────────────────────────────────────

@app.route("/knast")
@login_required
def knast_log():
    db = get_db()
    logs = db.execute(
        "SELECT * FROM knast_log ORDER BY created_at DESC"
    ).fetchall()
    active = db.execute(
        "SELECT * FROM knast ORDER BY jailed_at DESC"
    ).fetchall()
    db.close()
    return render_template("knast.html",
                           logs=[dict(r) for r in logs],
                           active=[dict(r) for r in active])


# ── Umfragen ──────────────────────────────────────────────────────────────────

@app.route("/umfragen")
@login_required
def umfragen():
    return render_template("umfragen.html")


@app.route("/api/umfragen/aktiv")
@login_required
def api_umfragen_aktiv():
    bot = current_app.config.get("BOT")
    if not bot:
        return jsonify([])
    cog = bot.cogs.get("Polls")
    if not cog:
        return jsonify([])
    return jsonify(cog.list_polls())


@app.route("/api/umfragen/erstellen", methods=["POST"])
@login_required
def api_umfragen_erstellen():
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    cog = bot.cogs.get("Polls")
    if not cog:
        return jsonify({"error": "Polls-Modul nicht geladen"}), 503

    data       = request.get_json() or {}
    channel_id = data.get("channel_id", "")
    question   = data.get("question", "").strip()
    options    = [o.strip() for o in data.get("options", []) if str(o).strip()][:5]

    if not channel_id or not question:
        return jsonify({"error": "Kanal und Frage erforderlich"}), 400
    if len(options) < 2:
        return jsonify({"error": "Mindestens 2 Optionen erforderlich"}), 400

    try:
        future = asyncio.run_coroutine_threadsafe(
            cog.create_poll(int(channel_id), question, options, "Dashboard"), loop
        )
        result = future.result(timeout=15)
        _discord_log("📊 Umfrage erstellt",
                     f"❓  **Frage:** {question}\n"
                     f"🗳️  **Optionen:** {', '.join(options)}\n"
                     f"📢  **Kanal:** #{result['channel']}")
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/umfragen/<message_id>/schliessen", methods=["POST"])
@login_required
def api_umfragen_schliessen(message_id):
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503
    cog = bot.cogs.get("Polls")
    if not cog:
        return jsonify({"error": "Polls-Modul nicht geladen"}), 503
    try:
        future = asyncio.run_coroutine_threadsafe(
            cog.close_poll(int(message_id)), loop
        )
        result = future.result(timeout=15)
        _discord_log("🔒 Umfrage geschlossen",
                     f"❓  **Frage:** {result['question']}\n"
                     f"🗳️  **Stimmen gesamt:** {result['total_votes']}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Statistiken ───────────────────────────────────────────────────────────────

@app.route("/statistiken")
@login_required
def statistiken():
    return render_template("statistiken.html")


@app.route("/api/statistiken/aktivitaet")
@login_required
def api_statistiken_aktivitaet():
    from datetime import date, timedelta
    days = request.args.get("days", 30, type=int)
    days = max(7, min(days, 90))
    db = get_db()
    try:
        start = str(date.today() - timedelta(days=days - 1))
        rows = db.execute(
            "SELECT date, message_count FROM daily_activity WHERE date >= ? ORDER BY date",
            (start,)
        ).fetchall()
        date_map = {r["date"]: r["message_count"] for r in rows}
    except Exception:
        date_map = {}
    finally:
        db.close()
    result = []
    for i in range(days):
        d = str(date.today() - timedelta(days=days - 1 - i))
        result.append({"date": d, "count": date_map.get(d, 0)})
    return jsonify(result)


@app.route("/api/statistiken/befehle")
@login_required
def api_statistiken_befehle():
    db = get_db()
    try:
        rows = db.execute(
            "SELECT command_name, COUNT(*) as count FROM command_log "
            "GROUP BY command_name ORDER BY count DESC LIMIT 15"
        ).fetchall()
        result = [dict(r) for r in rows]
    except Exception:
        result = []
    finally:
        db.close()
    return jsonify(result)


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

# ── Web-User-Verwaltung ───────────────────────────────────────────────────────

@app.route("/web-users")
@login_required
def web_users():
    db = get_db()
    rows = db.execute(
        "SELECT id, username, role, created_at FROM web_users ORDER BY created_at"
    ).fetchall()
    users = []
    for r in rows:
        u = dict(r)
        u["roles"] = _parse_roles(u["role"])
        users.append(u)
    db.close()
    return render_template("web_users.html", users=users)


@app.route("/api/web-users/create", methods=["POST"])
@login_required
def api_web_user_create():
    import json as _json
    data     = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    roles    = data.get("roles", data.get("role", "paten"))
    if isinstance(roles, str):
        roles = [roles]
    if not isinstance(roles, list) or not roles:
        roles = ["paten"]
    roles = [r for r in roles if r in VALID_ROLES] or ["paten"]
    if not username or not password:
        return jsonify({"error": "Benutzername und Passwort erforderlich"}), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO web_users (username, password_hash, role) VALUES (?,?,?)",
            (username, generate_password_hash(password), _json.dumps(roles))
        )
        db.commit()
        new_id = db.execute("SELECT id, created_at FROM web_users WHERE username=?", (username,)).fetchone()
        db.close()
    except Exception:
        db.close()
        return jsonify({"error": "Benutzername bereits vergeben"}), 409
    _discord_log("👤 Web-Nutzer erstellt",
                 f"**Nutzer:** {username} | **Rollen:** {', '.join(roles)} | **Von:** {session.get('username')}")
    return jsonify({"ok": True, "id": new_id["id"], "created_at": new_id["created_at"]})


@app.route("/api/web-users/<int:uid>/edit", methods=["POST"])
@login_required
def api_web_user_edit(uid):
    import json as _json
    data      = request.get_json() or {}
    new_roles = data.get("roles", data.get("role"))
    password  = data.get("password", "").strip()
    db = get_db()
    row = db.execute("SELECT username, role FROM web_users WHERE id=?", (uid,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Nutzer nicht gefunden"}), 404
    if new_roles is not None:
        if isinstance(new_roles, str):
            new_roles = [new_roles]
        new_roles = [r for r in new_roles if r in VALID_ROLES] or ["paten"]
        current_lvl = _user_level(_parse_roles(row["role"]))
        new_lvl     = _user_level(new_roles)
        if current_lvl >= 6 and new_lvl < 6:
            all_rows   = db.execute("SELECT role FROM web_users").fetchall()
            high_count = sum(1 for r in all_rows if _user_level(_parse_roles(r["role"])) >= 6)
            if high_count <= 1:
                db.close()
                return jsonify({"error": "Der letzte Owner/Developer kann nicht degradiert werden"}), 400
        db.execute("UPDATE web_users SET role=? WHERE id=?", (_json.dumps(new_roles), uid))
    if password:
        db.execute("UPDATE web_users SET password_hash=? WHERE id=?",
                   (generate_password_hash(password), uid))
    db.commit()
    db.close()
    _discord_log("✏️ Web-Nutzer bearbeitet",
                 f"**Nutzer:** {row['username']} | **Von:** {session.get('username')}")
    return jsonify({"ok": True})


@app.route("/api/web-users/<int:uid>/delete", methods=["POST"])
@login_required
def api_web_user_delete(uid):
    db = get_db()
    row = db.execute("SELECT username, role FROM web_users WHERE id=?", (uid,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Nutzer nicht gefunden"}), 404
    if row["username"] == session.get("username"):
        db.close()
        return jsonify({"error": "Du kannst deinen eigenen Account nicht löschen"}), 400
    if _user_level(_parse_roles(row["role"])) >= 6:
        all_rows   = db.execute("SELECT role FROM web_users").fetchall()
        high_count = sum(1 for r in all_rows if _user_level(_parse_roles(r["role"])) >= 6)
        if high_count <= 1:
            db.close()
            return jsonify({"error": "Der letzte Owner/Developer kann nicht gelöscht werden"}), 400
    db.execute("DELETE FROM web_users WHERE id=?", (uid,))
    db.commit()
    db.close()
    _discord_log("🗑️ Web-Nutzer gelöscht",
                 f"**Nutzer:** {row['username']} | **Von:** {session.get('username')}")
    return jsonify({"ok": True})


# ── Rollen-Berechtigungen ─────────────────────────────────────────────────────

@app.route("/role-permissions")
@login_required
def role_permissions():
    perms = _load_permissions()
    grid: dict = {}
    for feat_key in FEATURES:
        grid[feat_key] = {role: feat_key in perms.get(role, set()) for role in VALID_ROLES}
    return render_template("role_permissions.html",
                           features=FEATURES, roles=VALID_ROLES, grid=grid)


@app.route("/api/role-permissions/save", methods=["POST"])
@login_required
def api_role_permissions_save():
    import json as _j
    data    = request.get_json() or {}
    role    = data.get("role")
    feature = data.get("feature")
    enabled = bool(data.get("enabled", False))
    if role not in VALID_ROLES or feature not in FEATURES:
        return jsonify({"error": "Ungültige Rolle oder Feature"}), 400
    if role == "developer":
        return jsonify({"error": "Developer-Berechtigungen sind fest"}), 400
    if feature in DEV_ONLY_FEATURES:
        return jsonify({"error": "Dieses Feature ist nur für Developer verfügbar"}), 403
    db = get_db()
    row = db.execute("SELECT permissions FROM role_permissions WHERE role=?", (role,)).fetchone()
    perms = set(_j.loads(row["permissions"])) if row else set(DEFAULT_PERMISSIONS.get(role, []))
    if enabled:
        perms.add(feature)
    else:
        perms.discard(feature)
    db.execute(
        "INSERT INTO role_permissions (role, permissions) VALUES (?,?)"
        " ON CONFLICT(role) DO UPDATE SET permissions=excluded.permissions",
        (role, _j.dumps(sorted(perms)))
    )
    db.commit()
    db.close()
    _invalidate_perm_cache()
    action = "aktiviert" if enabled else "deaktiviert"
    feat_label = FEATURES[feature]["label"]
    _discord_log("🛡️ Berechtigung geändert",
                 f"🎭  **Rolle:** {role}\n"
                 f"🔧  **Feature:** {feat_label}\n"
                 f"🔘  **Status:** {'✅' if enabled else '⛔'} {action}\n"
                 f"🌐  **Von:** {session.get('username')}")
    return jsonify({"ok": True})


# ── Regelwerk-Editor ──────────────────────────────────────────────────────────

@app.route("/regelwerk-editor", methods=["GET", "POST"])
@login_required
def regelwerk_editor_page():
    import json as _j
    rules = _load_regelwerk()
    if request.method == "POST":
        titles   = request.form.getlist("title")
        contents = request.form.getlist("content")
        new_rules = [
            {"title": t.strip(), "content": c.strip()}
            for t, c in zip(titles, contents)
            if t.strip()
        ]
        if new_rules:
            db = get_db()
            db.execute(
                "INSERT INTO bot_settings (key, value) VALUES ('regelwerk_rules', ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (_j.dumps(new_rules),)
            )
            db.commit()
            db.close()
            _discord_log("📜 Regelwerk aktualisiert",
                         f"📝  **Abschnitte:** {len(new_rules)}\n"
                         f"🌐  **Von:** {session.get('username')}")
        return redirect(url_for("regelwerk_editor_page"))
    return render_template("regelwerk_editor.html", rules=rules)


@app.route("/api/regelwerk/post", methods=["POST"])
@login_required
def api_regelwerk_post():
    bot  = current_app.config.get("BOT")
    loop = current_app.config.get("LOOP")
    if not bot or not loop:
        return jsonify({"error": "Bot nicht verfügbar"}), 503

    # Regeln im Flask-Thread laden (kein DB-Zugriff im Bot-Loop nötig)
    rules = _load_regelwerk()

    async def _post():
        import discord as _d
        import sys as _sys
        # Cog ist bereits vom Bot geladen → direkt aus sys.modules holen
        mod = _sys.modules.get("cogs.regelwerk")
        if mod is None:
            raise RuntimeError("Regelwerk-Cog nicht geladen")
        RulesAcceptView  = mod.RulesAcceptView
        RULES_CHANNEL_ID = mod.RULES_CHANNEL_ID

        channel = bot.get_channel(RULES_CHANNEL_ID)
        if not channel:
            raise ValueError(f"Kanal {RULES_CHANNEL_ID} nicht gefunden")

        embed = _d.Embed(
            title="📜 Discord Server Regeln",
            description=(
                "Bitte lies die folgenden Regeln sorgfältig durch.\n"
                "Mit dem Klick auf den Button unten bestätigst du, dass du sie gelesen und akzeptiert hast."
            ),
            color=_d.Color.from_rgb(88, 101, 242),
        )
        for rule in rules:
            embed.add_field(name=rule["title"][:256], value=rule["content"][:1024], inline=False)
        embed.set_footer(text="Durch den Klick auf ✅ bekommst du Zugang zum Server.")
        await channel.send(embed=embed, view=RulesAcceptView())

    try:
        asyncio.run_coroutine_threadsafe(_post(), loop).result(timeout=15)
        _discord_log("📜 Regelwerk in Discord gepostet", f"🌐  **Von:** {session.get('username')}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Verified ──────────────────────────────────────────────────────────────────

@app.route("/verified")
@login_required
def verified_page():
    db = get_db()
    try:
        rows = db.execute(
            "SELECT user_id, username, verified_at FROM verified_users ORDER BY verified_at DESC"
        ).fetchall()
        users = [dict(r) for r in rows]
    except Exception:
        users = []
    finally:
        db.close()
    return render_template("verified.html", users=users)


@app.route("/api/verified/<int:user_id>/delete", methods=["POST"])
@login_required
def api_verified_delete(user_id):
    db = get_db()
    row = db.execute("SELECT username FROM verified_users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Nutzer nicht gefunden"}), 404
    db.execute("DELETE FROM verified_users WHERE user_id=?", (user_id,))
    db.commit()
    db.close()
    _discord_log("🗑️ Verified-Eintrag entfernt",
                 f"👤  **Nutzer:** {row['username']} (`{user_id}`)\n"
                 f"🌐  **Von:** {session.get('username')}")
    return jsonify({"ok": True})


# ── Verwarnungen ─────────────────────────────────────────────────────────────

@app.route("/warns")
@login_required
def warns_page():
    db = get_db()
    try:
        rows = db.execute("""
            SELECT user_id, username,
                   COALESCE(SUM(amount), 0) AS total,
                   MAX(warned_at) AS last_warn
            FROM warns
            GROUP BY user_id
            ORDER BY total DESC, last_warn DESC
        """).fetchall()
        users = [dict(r) for r in rows]
        history = {}
        for u in users:
            h = db.execute("""
                SELECT amount, reason, moderator_name, warned_at
                FROM warns WHERE user_id = ?
                ORDER BY warned_at DESC LIMIT 10
            """, (u["user_id"],)).fetchall()
            history[u["user_id"]] = [dict(r) for r in h]
    except Exception:
        users, history = [], {}
    finally:
        db.close()
    return render_template("warns.html", users=users, history=history, auto_jail=5)


@app.route("/api/warns/<int:user_id>/clear", methods=["POST"])
@login_required
def api_warns_clear(user_id):
    db = get_db()
    row = db.execute("SELECT username FROM warns WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
    if not row:
        db.close()
        return jsonify({"error": "Keine Verwarnungen gefunden"}), 404
    db.execute("DELETE FROM warns WHERE user_id=?", (user_id,))
    db.commit()
    db.close()
    _discord_log("🗑️ Verwarnungen gelöscht",
                 f"👤  **Nutzer:** {row['username']} (`{user_id}`)\n"
                 f"🌐  **Von:** {session.get('username')}")
    return jsonify({"ok": True})


# ── Emoji Quiz ───────────────────────────────────────────────────────────────

@app.route("/emoji-quiz")
@login_required
def emoji_quiz_page():
    db = get_db()
    try:
        leaderboard = db.execute(
            "SELECT username, aepfel FROM users WHERE aepfel > 0 ORDER BY aepfel DESC LIMIT 50"
        ).fetchall()
        leaderboard = [dict(r) for r in leaderboard]
        stats = {
            "total_bananen": db.execute("SELECT COALESCE(SUM(aepfel),0) FROM users").fetchone()[0] or 0,
            "total_players": db.execute("SELECT COUNT(*) FROM users WHERE aepfel > 0").fetchone()[0] or 0,
            "top_player":    leaderboard[0]["username"] if leaderboard else "—",
            "top_bananen":   leaderboard[0]["aepfel"]   if leaderboard else 0,
        }
    except Exception:
        leaderboard, stats = [], {"total_bananen": 0, "total_players": 0, "top_player": "—", "top_bananen": 0}
    finally:
        db.close()
    return render_template("emoji_quiz.html", leaderboard=leaderboard, stats=stats)


# ── Server-Log ────────────────────────────────────────────────────────────────

_VALID_LOG_CATS = {"all", "member", "moderation", "message", "voice", "server", "ticket", "bot"}
_LOG_PAGE_SIZE  = 100


@app.route("/log")
@login_required
def server_log_page():
    _vroles = session.get("roles", ["paten"])
    _perms  = _load_permissions()
    if not any("server_log" in _perms.get(r, set()) for r in _vroles):
        return render_template("403.html", role=", ".join(_vroles)), 403

    category = request.args.get("category", "all").lower()
    if category not in _VALID_LOG_CATS:
        category = "all"
    q    = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    offset = (page - 1) * _LOG_PAGE_SIZE

    db = get_db()
    try:
        where_parts, params = [], []
        if category != "all":
            where_parts.append("category = ?")
            params.append(category)
        if q:
            where_parts.append("(action LIKE ? OR username LIKE ? OR target_name LIKE ? OR details LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like, like])
        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        total   = db.execute(f"SELECT COUNT(*) FROM server_log {where_sql}", params).fetchone()[0]
        rows    = db.execute(
            f"SELECT * FROM server_log {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [_LOG_PAGE_SIZE, offset],
        ).fetchall()
        entries = [dict(r) for r in rows]
    except Exception:
        total, entries = 0, []
    finally:
        db.close()

    total_pages = max(1, (total + _LOG_PAGE_SIZE - 1) // _LOG_PAGE_SIZE)
    return render_template("server_log.html",
        entries=entries, category=category, q=q,
        page=page, total=total, total_pages=total_pages,
    )


@app.route("/api/log/clear", methods=["POST"])
@login_required
def api_log_clear():
    _vroles = session.get("roles", ["paten"])
    if "developer" not in _vroles:
        return jsonify({"error": "Nur Developer können den Log leeren"}), 403
    category = (request.get_json() or {}).get("category", "all")
    db = get_db()
    try:
        if category == "all" or category not in _VALID_LOG_CATS:
            db.execute("DELETE FROM server_log")
        else:
            db.execute("DELETE FROM server_log WHERE category = ?", (category,))
        db.commit()
    finally:
        db.close()
    _discord_log("🗑️ Server-Log geleert",
                 f"📂  **Kategorie:** {category}\n🌐  **Von:** {session.get('username')}")
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
