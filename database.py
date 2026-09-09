import datetime as _datetime
import os
import sqlite3

DB_FILE = "gymtrack.db"
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
IS_POSTGRES = DATABASE_URL.startswith('postgres://') or DATABASE_URL.startswith('postgresql://')


class DbRow(dict):
    """Row that supports both column-name access (row['id']) and positional
    access (row[0]), so the rest of the code is backend-agnostic."""

    def __getitem__(self, key):
        if isinstance(key, int):
            keys = list(self.keys())
            return super().__getitem__(keys[key])
        return super().__getitem__(key)


def _rowify(row):
    if row is None:
        return None
    try:
        d = dict(row)
    except Exception:
        d = dict(row)
    # Normalize datetime/date columns to ISO strings (matches SQLite storage),
    # so templates/code that slice or format timestamps work on both backends.
    for key, value in list(d.items()):
        if isinstance(value, (_datetime.date, _datetime.datetime)):
            d[key] = value.isoformat()
    return DbRow(d)


# ── SQLite backend (local development) ──────────────────────────────

class _SqliteCursor:
    def __init__(self, conn):
        self._conn = conn
        self._raw = conn.cursor()

    @property
    def lastrowid(self):
        return self._raw.lastrowid

    def execute(self, sql, params=None):
        self._raw.execute(sql, params if params is not None else ())
        return self

    def executemany(self, sql, seq):
        self._raw.executemany(sql, seq)
        return self

    def fetchone(self):
        return _rowify(self._raw.fetchone())

    def fetchall(self):
        return [_rowify(r) for r in self._raw.fetchall()]


class _SqliteConn:
    def __init__(self):
        self._raw = sqlite3.connect(DB_FILE)
        self._raw.row_factory = sqlite3.Row
        self._closed = False

    def cursor(self):
        return _SqliteCursor(self._raw)

    def commit(self):
        self._raw.commit()

    def close(self):
        if not self._closed:
            self._raw.close()
            self._closed = True


# ── Postgres backend (Vercel / serverless) ──────────────────────────

_pg_pool = None
_pg_pool_backend = None


def _get_pg_pool():
    global _pg_pool, _pg_pool_backend
    if _pg_pool is None or _pg_pool_backend != DATABASE_URL:
        import psycopg
        from psycopg_pool import ConnectionPool

        _pg_pool = ConnectionPool(
            DATABASE_URL,
            min_size=0,
            max_size=5,
            timeout=8,
            open=False,
            kwargs={
                'row_factory': psycopg.rows.dict_row,
                'connect_timeout': 8,
                'autocommit': True,
            },
        )
        _pg_pool.open()
        _pg_pool_backend = DATABASE_URL
    return _pg_pool


def _translate_sql(sql):
    """Convert the shared (SQLite-flavoured) SQL dialed for Postgres."""
    if 'INSERT OR IGNORE INTO' in sql:
        sql = sql.replace('INSERT OR IGNORE INTO', 'INSERT INTO').rstrip('; \n\t')
        sql += ' ON CONFLICT DO NOTHING'
    return sql.replace('?', '%s')


class _PgCursor:
    def __init__(self, pg_conn):
        self._pg_conn = pg_conn
        self._raw = pg_conn._raw.cursor()
        self._lastrowid = None

    @property
    def lastrowid(self):
        return self._lastrowid

    def execute(self, sql, params=None):
        translated = _translate_sql(sql)
        is_insert = translated.lstrip().startswith('INSERT INTO')
        if is_insert and ' RETURNING ' not in translated.upper():
            translated = translated.rstrip('; \n\t') + ' RETURNING id'
        self._raw.execute(translated, params if params is not None else ())
        self._lastrowid = None
        if is_insert:
            row = self._raw.fetchone()
            if row is not None:
                self._lastrowid = row['id']
        return self

    def executemany(self, sql, seq):
        translated = _translate_sql(sql)
        self._raw.executemany(translated, seq)
        return self

    def fetchone(self):
        return _rowify(self._raw.fetchone())

    def fetchall(self):
        return [_rowify(r) for r in self._raw.fetchall()]


class _PgConn:
    def __init__(self):
        pool = _get_pg_pool()
        self._pool = pool
        self._raw = pool.getconn()
        self._closed = False

    def cursor(self):
        return _PgCursor(self)

    def commit(self):
        self._raw.commit()

    def close(self):
        if not self._closed:
            self._pool.putconn(self._raw)
            self._closed = True


def get_db():
    return _PgConn() if IS_POSTGRES else _SqliteConn()


# ── Schema ──────────────────────────────────────────────────────────

def _ensure_users_columns(c):
    """Add newer columns that may be missing on existing databases."""
    if IS_POSTGRES:
        for col, ddl in [
            ('phone', 'TEXT'), ('bio', 'TEXT'), ('fitness_goal', 'TEXT'),
            ('is_verified', 'INTEGER DEFAULT 0'), ('verification_token', 'TEXT'),
            ('username', 'TEXT'), ('google_id', 'TEXT'),
            ('account_status', "TEXT DEFAULT 'active'"),
            ('delete_email_code', 'TEXT'), ('delete_email_code_expiry', 'TIMESTAMP'),
            ('delete_reason', 'TEXT'), ('delete_requested_at', 'TIMESTAMP'),
            ('restore_token', 'TEXT'), ('avatar', 'TEXT'),
            ('avatar_data', 'BYTEA'), ('avatar_mime', 'TEXT'),
        ]:
            c.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}")
    else:
        try:
            c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN bio TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN fitness_goal TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
            c.execute("UPDATE users SET is_verified = 1")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN username TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN account_status TEXT DEFAULT 'active'")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN delete_email_code TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN delete_email_code_expiry TIMESTAMP")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN delete_reason TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN delete_requested_at TIMESTAMP")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN restore_token TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN avatar_data BLOB")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE users ADD COLUMN avatar_mime TEXT")
        except Exception:
            pass


def init_db():
    conn = get_db()
    c = conn.cursor()

    if IS_POSTGRES:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT,
                bio TEXT,
                fitness_goal TEXT,
                password_hash TEXT NOT NULL,
                reset_token TEXT,
                reset_token_expiry TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                first_name TEXT,
                last_name TEXT,
                is_verified INTEGER DEFAULT 0,
                verification_token TEXT,
                username TEXT,
                google_id TEXT,
                account_status TEXT DEFAULT 'active',
                delete_email_code TEXT,
                delete_email_code_expiry TIMESTAMP,
                delete_reason TEXT,
                delete_requested_at TIMESTAMP,
                restore_token TEXT,
                avatar TEXT,
                avatar_data BYTEA,
                avatar_mime TEXT
            )
        """)
    else:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT,
                bio TEXT,
                fitness_goal TEXT,
                password_hash TEXT NOT NULL,
                reset_token TEXT,
                reset_token_expiry TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # One-time migration: populate first_name/last_name from existing name
    # (SQLite-only — fresh Postgres tables always include the columns)
    if not IS_POSTGRES and 'first_name' in [col['name'] for col in c.execute('PRAGMA table_info(users)').fetchall()]:
        c.execute("UPDATE users SET first_name = name WHERE first_name IS NULL")
        c.execute("UPDATE users SET last_name = '' WHERE last_name IS NULL")
    _ensure_users_columns(c)

    if IS_POSTGRES:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id)")
    else:
        try:
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        except Exception:
            pass
        try:
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id)")
        except Exception:
            pass

    pk = "id INTEGER PRIMARY KEY AUTOINCREMENT" if not IS_POSTGRES else "id SERIAL PRIMARY KEY"

    # Workout plan — per user
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS workout_plan (
            {pk},
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            exercise TEXT NOT NULL,
            UNIQUE(user_id, day, exercise)
        )
    """)

    # Progress — per user
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS progress (
            {pk},
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            exercise TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            UNIQUE(user_id, day, exercise)
        )
    """)

    # History — per user
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS history (
            {pk},
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            exercise TEXT NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Streaks — per user
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS streaks (
            {pk},
            user_id INTEGER NOT NULL,
            workout_date DATE NOT NULL,
            UNIQUE(user_id, workout_date)
        )
    """)

    # Exercise notes — per user
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS exercise_notes (
            {pk},
            user_id INTEGER NOT NULL,
            exercise TEXT NOT NULL,
            note TEXT,
            UNIQUE(user_id, exercise)
        )
    """)

    # Chat sessions — per user
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            {pk},
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Chat messages — belong to a session
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS chat_messages (
            {pk},
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def seed_default_plan(user_id):
    """Give a new user the default workout plan."""
    default_plan = {
        "Day 1 (Chest)": ["Push-ups", "Bench Press", "Chest Fly"],
        "Day 2 (Legs)": ["Squats", "Lunges", "Leg Press"],
        "Day 3 (Back)": ["Pull-ups", "Deadlift", "Lat Pulldown"],
        "Day 4 (Shoulders)": ["Shoulder Press", "Lateral Raises", "Shrugs"],
        "Day 5 (Arms)": ["Bicep Curls", "Tricep Dips", "Hammer Curls"],
        "Day 6 (Core)": ["Plank", "Crunches", "Leg Raises"],
        "Day 7 (Rest)": ["Rest Day - Light Stretching / Recovery"],
        "Day 8 (Full Body)": ["Burpees", "Mountain Climbers", "Jumping Jacks"],
        "Day Special (Cardio)": ["Running", "Cycling", "Jump Rope"]
    }

    conn = get_db()
    c = conn.cursor()
    for day, exercises in default_plan.items():
        for exercise in exercises:
            c.execute(
                "INSERT OR IGNORE INTO workout_plan (user_id, day, exercise) VALUES (?, ?, ?)",
                (user_id, day, exercise)
            )
            c.execute(
                "INSERT OR IGNORE INTO progress (user_id, day, exercise, completed) VALUES (?, ?, ?, 0)",
                (user_id, day, exercise)
            )
    conn.commit()
    conn.close()


def init_ai_exercise_details_table():
    """Create table for AI generated exercise details."""
    pk = "id INTEGER PRIMARY KEY AUTOINCREMENT" if not IS_POSTGRES else "id SERIAL PRIMARY KEY"
    conn = get_db()
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS ai_exercise_details (
            {pk},
            exercise_name TEXT NOT NULL UNIQUE,
            muscle TEXT,
            difficulty TEXT,
            equipment TEXT,
            summary TEXT,
            benefits TEXT,
            how_to TEXT,
            sets_reps TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def init_feedback_table():
    """Create table for visitor feedback submissions."""
    pk = "id INTEGER PRIMARY KEY AUTOINCREMENT" if not IS_POSTGRES else "id SERIAL PRIMARY KEY"
    conn = get_db()
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS feedback (
            {pk},
            category TEXT NOT NULL DEFAULT 'General',
            name TEXT,
            email TEXT,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migrate existing tables — add reply workflow columns if missing
    if IS_POSTGRES:
        for col, ddl in [
            ('status', "TEXT DEFAULT 'new'"),
            ('reply', 'TEXT'),
            ('replied_at', 'TIMESTAMP'),
        ]:
            c.execute(f"ALTER TABLE feedback ADD COLUMN IF NOT EXISTS {col} {ddl}")
    else:
        for sql in [
            "ALTER TABLE feedback ADD COLUMN status TEXT DEFAULT 'new'",
            "ALTER TABLE feedback ADD COLUMN reply TEXT",
            "ALTER TABLE feedback ADD COLUMN replied_at TIMESTAMP",
        ]:
            try:
                c.execute(sql)
            except Exception:
                pass
    conn.commit()
    conn.close()