import sqlite3
import json
import os

DB_FILE = "gymtrack.db"


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # Users table
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

    # Add new columns if they don't exist (for existing databases)
    try:
        c.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
    except Exception:
        pass
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

    # One-time migration: populate first_name/last_name from existing name
    if 'first_name' in [col['name'] for col in c.execute('PRAGMA table_info(users)').fetchall()]:
        c.execute("UPDATE users SET first_name = name WHERE first_name IS NULL")
        c.execute("UPDATE users SET last_name = '' WHERE last_name IS NULL")
    try:
        c.execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN username TEXT")
    except Exception:
        pass
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
    except Exception:
        pass
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id)")
    except Exception:
        pass

    # ── Account lifecycle (Meta-style deactivate / delete-with-grace-period) ──
    # account_status: 'active' | 'deactivated' | 'pending_delete'
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
    conn.commit()

    # Workout plan — per user
    c.execute("""
        CREATE TABLE IF NOT EXISTS workout_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            exercise TEXT NOT NULL,
            UNIQUE(user_id, day, exercise),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Progress — per user
    c.execute("""
        CREATE TABLE IF NOT EXISTS progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            exercise TEXT NOT NULL,
            completed INTEGER DEFAULT 0,
            UNIQUE(user_id, day, exercise),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # History — per user
    c.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            exercise TEXT NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Streaks — per user
    c.execute("""
        CREATE TABLE IF NOT EXISTS streaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workout_date DATE NOT NULL,
            UNIQUE(user_id, workout_date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Exercise notes — per user
    c.execute("""
        CREATE TABLE IF NOT EXISTS exercise_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            exercise TEXT NOT NULL,
            note TEXT,
            UNIQUE(user_id, exercise),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Chat sessions — per user (Gemini-style conversation history)
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Chat messages — belong to a session
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
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
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_exercise_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT 'General',
            name TEXT,
            email TEXT,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migrate existing tables — add reply workflow columns if missing
    try:
        c.execute("ALTER TABLE feedback ADD COLUMN status TEXT DEFAULT 'new'")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE feedback ADD COLUMN reply TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE feedback ADD COLUMN replied_at TIMESTAMP")
    except Exception:
        pass
    conn.commit()
    conn.close()