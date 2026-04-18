import aiosqlite

import os
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "gamingbot.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class Database:
    def __init__(self):
        self.db_path = DB_PATH

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT    NOT NULL,
                    coins       INTEGER DEFAULT 500,
                    wins        INTEGER DEFAULT 0,
                    losses      INTEGER DEFAULT 0,
                    draws       INTEGER DEFAULT 0,
                    total_spins INTEGER DEFAULT 0,
                    last_daily  TEXT    DEFAULT NULL,
                    xp          INTEGER DEFAULT 0,
                    level       INTEGER DEFAULT 0
                )
            """)
            # Migration für bestehende Datenbanken
            for col, definition in [
                ("xp",               "INTEGER DEFAULT 0"),
                ("level",            "INTEGER DEFAULT 0"),
                ("streak",           "INTEGER DEFAULT 0"),
                ("last_streak_date", "TEXT DEFAULT NULL"),
                ("max_streak",       "INTEGER DEFAULT 0"),
                ("message_count",    "INTEGER DEFAULT 0"),
                ("voice_minutes",    "INTEGER DEFAULT 0"),
                ("voice_seconds",    "INTEGER DEFAULT 0"),
                ("name_protected",   "INTEGER DEFAULT 0"),
            ]:
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                except Exception:
                    pass
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_activity (
                    date          TEXT PRIMARY KEY,
                    message_count INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS command_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_name TEXT NOT NULL,
                    used_at      TEXT DEFAULT (date('now'))
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS knast (
                    user_id   INTEGER PRIMARY KEY,
                    guild_id  INTEGER NOT NULL,
                    roles     TEXT    NOT NULL DEFAULT '[]',
                    reason    TEXT    DEFAULT NULL,
                    jailed_by TEXT    DEFAULT NULL,
                    jailed_at TEXT    DEFAULT (datetime('now'))
                )
            """)
            await db.commit()
        print("✅ Datenbank bereit")

    # ── helpers ──────────────────────────────────────────────────────────────

    async def get_user(self, user_id: int, username: str) -> dict:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            if row is None:
                await db.execute(
                    "INSERT INTO users (user_id, username) VALUES (?, ?)",
                    (user_id, username),
                )
                await db.commit()
            elif not dict(row).get("name_protected", 0) and dict(row)["username"] != username:
                await db.execute(
                    "UPDATE users SET username = ? WHERE user_id = ?",
                    (username, user_id),
                )
                await db.commit()
            cur = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            return dict(row)

    async def set_name_protected(self, user_id: int, protected: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET name_protected = ? WHERE user_id = ?",
                (1 if protected else 0, user_id),
            )
            await db.commit()

    async def get_coins(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            return row[0] if row else 0

    async def update_coins(self, user_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET coins = MAX(0, coins + ?) WHERE user_id = ?",
                (amount, user_id),
            )
            await db.commit()

    async def add_win(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
            await db.commit()

    async def add_loss(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
            await db.commit()

    async def add_draw(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET draws = draws + 1 WHERE user_id = ?", (user_id,))
            await db.commit()

    async def add_spin(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET total_spins = total_spins + 1 WHERE user_id = ?", (user_id,)
            )
            await db.commit()

    async def get_leaderboard(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM users ORDER BY coins DESC LIMIT ?", (limit,)
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_last_daily(self, user_id: int) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            return row[0] if row else None

    async def set_last_daily(self, user_id: int, date_str: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET last_daily = ? WHERE user_id = ?", (date_str, user_id)
            )
            await db.commit()

    async def add_xp(self, user_id: int, amount: int) -> tuple[int, int]:
        """Fügt XP hinzu und aktualisiert das Level. Gibt (altes_level, neues_level) zurück."""
        from utils import level_from_xp
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            if row is None:
                return 0, 0
            old_xp, old_level = row
            new_xp = old_xp + amount
            new_level = level_from_xp(new_xp)
            await db.execute(
                "UPDATE users SET xp = ?, level = ? WHERE user_id = ?",
                (new_xp, new_level, user_id),
            )
            await db.commit()
        return old_level, new_level

    async def add_message(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET message_count = message_count + 1 WHERE user_id = ?", (user_id,)
            )
            await db.commit()

    async def add_voice_seconds(self, user_id: int, seconds: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET voice_seconds = voice_seconds + ? WHERE user_id = ?", (seconds, user_id)
            )
            await db.commit()

    async def get_chat_voice_stats(self, user_id: int) -> tuple[int, int]:
        """Gibt (message_count, voice_seconds) zurück."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT message_count, voice_seconds FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cur.fetchone()
            return (row[0] or 0, row[1] or 0) if row else (0, 0)

    async def get_chat_leaderboard(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM users ORDER BY message_count DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in await cur.fetchall()]

    async def get_voice_leaderboard(self, limit: int = 10) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM users ORDER BY voice_seconds DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in await cur.fetchall()]

    async def update_streak(self, user_id: int) -> tuple[int, int]:
        """Aktualisiert den Streak. Gibt (alter_streak, neuer_streak) zurück."""
        from datetime import date, timedelta
        today = str(date.today())
        yesterday = str(date.today() - timedelta(days=1))

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT streak, last_streak_date, max_streak FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cur.fetchone()
            if row is None:
                return 0, 0
            old_streak, last_date, max_streak = row

            if last_date == today:
                return old_streak, old_streak  # bereits heute gezählt

            if last_date == yesterday:
                new_streak = old_streak + 1
            else:
                new_streak = 1  # Streak gebrochen oder erster Tag

            new_max = max(max_streak or 0, new_streak)
            await db.execute(
                "UPDATE users SET streak = ?, last_streak_date = ?, max_streak = ? WHERE user_id = ?",
                (new_streak, today, new_max, user_id),
            )
            await db.commit()
        return old_streak, new_streak

    async def get_streak(self, user_id: int) -> tuple[int, int]:
        """Gibt (streak, max_streak) zurück."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT streak, max_streak FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cur.fetchone()
            return (row[0] or 0, row[1] or 0) if row else (0, 0)

    async def log_daily_message(self):
        from datetime import date
        today = str(date.today())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO daily_activity (date, message_count) VALUES (?, 1)
                ON CONFLICT(date) DO UPDATE SET message_count = message_count + 1
            """, (today,))
            await db.commit()

    async def log_command(self, command_name: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO command_log (command_name) VALUES (?)", (command_name,)
            )
            await db.commit()

    async def get_xp(self, user_id: int) -> tuple[int, int]:
        """Gibt (xp, level) zurück."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            return (row[0], row[1]) if row else (0, 0)
