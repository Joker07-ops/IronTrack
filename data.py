from database import get_db
from datetime import datetime, date, timedelta
import secrets


def secrets_token():
    return secrets.token_urlsafe(32)


# ── WORKOUT PLAN ──────────────────────────

def load_workout(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT day, exercise FROM workout_plan WHERE user_id=? ORDER BY id", (user_id,))
    rows = c.fetchall()
    conn.close()
    plan = {}
    for row in rows:
        if row["exercise"] == '__hidden__':
            # Keep the day key alive but don't add the hidden exercise
            if row["day"] not in plan:
                plan[row["day"]] = []
            continue
        if row["day"] not in plan:
            plan[row["day"]] = []
        plan[row["day"]].append(row["exercise"])
    return plan


def save_workout_exercise(user_id, day, exercise):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO workout_plan (user_id, day, exercise) VALUES (?, ?, ?)",
              (user_id, day, exercise))
    conn.commit()
    conn.close()


def delete_workout_exercise(user_id, day, exercise):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM progress WHERE user_id=? AND day=? AND exercise=?",
              (user_id, day, exercise))
    c.execute("DELETE FROM workout_plan WHERE user_id=? AND day=? AND exercise=?",
              (user_id, day, exercise))
    # Check if the day still has any visible exercises
    c.execute("SELECT COUNT(*) FROM workout_plan WHERE user_id=? AND day=? AND exercise!=?",
              (user_id, day, '__hidden__'))
    count = c.fetchone()[0]
    if count == 0:
        # Day is now empty — insert a hidden marker so the day key survives
        c.execute("INSERT OR IGNORE INTO workout_plan (user_id, day, exercise) VALUES (?, ?, ?)",
                  (user_id, day, '__hidden__'))
    conn.commit()
    conn.close()



# ── PROGRESS ─────────────────────────────

def load_progress(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT day, exercise, completed FROM progress WHERE user_id=? ORDER BY id",
              (user_id,))
    rows = c.fetchall()
    conn.close()
    progress = {}
    for row in rows:
        if row["day"] not in progress:
            progress[row["day"]] = {}
        progress[row["day"]][row["exercise"]] = bool(row["completed"])
    return progress


def save_progress(user_id, day, exercise, completed):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO progress (user_id, day, exercise, completed) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, day, exercise) DO UPDATE SET completed=excluded.completed",
        (user_id, day, exercise, 1 if completed else 0)
    )
    conn.commit()
    conn.close()


# ── HISTORY ──────────────────────────────

def add_to_history(user_id, day, exercise):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO history (user_id, day, exercise) VALUES (?, ?, ?)",
              (user_id, day, exercise))
    conn.commit()
    conn.close()


def get_history(user_id, limit=100):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT day, exercise, completed_at FROM history WHERE user_id=? "
        "ORDER BY completed_at DESC LIMIT ?",
        (user_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── STREAKS ──────────────────────────────

def log_workout_date(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO streaks (user_id, workout_date) VALUES (?, ?)",
              (user_id, str(date.today())))
    conn.commit()
    conn.close()


def get_streak(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT workout_date FROM streaks WHERE user_id=? ORDER BY workout_date DESC",
              (user_id,))
    rows = [r["workout_date"] for r in c.fetchall()]
    conn.close()
    if not rows:
        return 0
    streak = 0
    check = date.today()
    for row in rows:
        d = row if isinstance(row, date) else date.fromisoformat(row)
        if d == check or d == check - timedelta(days=1):
            streak += 1
            check = d - timedelta(days=1)
        else:
            break
    return streak


# ── NOTES ────────────────────────────────

def get_note(user_id, exercise):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT note FROM exercise_notes WHERE user_id=? AND exercise=?",
              (user_id, exercise))
    row = c.fetchone()
    conn.close()
    return row["note"] if row else ""


def save_note(user_id, exercise, note):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO exercise_notes (user_id, exercise, note) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, exercise) DO UPDATE SET note=excluded.note",
        (user_id, exercise, note)
    )
    conn.commit()
    conn.close()


# ── USER AUTH ────────────────────────────

def get_user_by_username(username):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(name, email, password_hash, verification_token=None, first_name=None, last_name=None, username=None):
    conn = get_db()
    c = conn.cursor()
    if not first_name and ' ' in name:
        first_name = name.rsplit(' ', 1)[0]
        last_name = name.rsplit(' ', 1)[1]
    elif not first_name:
        first_name = name
        last_name = ''
    if not username:
        username = email.split('@')[0]
    c.execute(
        "INSERT INTO users (name, email, password_hash, is_verified, verification_token, first_name, last_name, username) "
        "VALUES (?, ?, ?, 0, ?, ?, ?, ?)",
        (name, email, password_hash, verification_token, first_name, last_name, username)
    )
    user_id = c.lastrowid
    conn.commit()
    conn.close()
    return user_id


def set_reset_token(email, token, expiry):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET reset_token=?, reset_token_expiry=? WHERE email=?",
        (token, expiry, email)
    )
    conn.commit()
    conn.close()


def get_user_by_reset_token(token):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE reset_token=?", (token,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_password(user_id, password_hash):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET password_hash=?, reset_token=NULL, reset_token_expiry=NULL WHERE id=?",
        (password_hash, user_id)
    )
    conn.commit()
    conn.close()


# ── GOOGLE OAUTH ─────────────────────────

def get_user_by_google_id(google_id):
    if not google_id:
        return None
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE google_id=?", (google_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def link_google_id(user_id, google_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET google_id=?, is_verified=1 WHERE id=?",
              (google_id, user_id))
    conn.commit()
    conn.close()


def create_google_user(name, email, google_id, username=None,
                       first_name=None, last_name=None):
    from secrets import token_hex
    from werkzeug.security import generate_password_hash

    if not username:
        base = (email.split('@')[0] if email else 'user') or 'user'
        username = base
        # Ensure uniqueness
        conn = get_db()
        c = conn.cursor()
        i = 1
        while True:
            c.execute("SELECT id FROM users WHERE username=?", (username,))
            if not c.fetchone():
                break
            username = f"{base}{i}"
            i += 1
        conn.close()

    # Random password so this account can never be logged into via password alone
    password_hash = generate_password_hash(token_hex(24))
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (name, email, password_hash, is_verified, first_name, last_name, username, google_id) "
        "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
        (name, email, password_hash, first_name, last_name, username, google_id)
    )
    user_id = c.lastrowid
    conn.commit()
    conn.close()
    return user_id


# ── AI EXERCISE DETAILS ───────────────────

def get_ai_exercise_details(exercise_name):
    """Get AI generated details for an exercise."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM ai_exercise_details WHERE exercise_name=?", (exercise_name,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    # Parse JSON fields
    import json
    try:
        data['benefits'] = json.loads(data['benefits']) if data['benefits'] else []
        data['how_to']   = json.loads(data['how_to'])   if data['how_to']   else []
    except Exception:
        data['benefits'] = []
        data['how_to']   = []
    return data


def save_ai_exercise_details(exercise_name, details):
    """Save AI generated details for an exercise."""
    import json
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO ai_exercise_details
            (exercise_name, muscle, difficulty, equipment, summary, benefits, how_to, sets_reps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exercise_name) DO UPDATE SET
            muscle=excluded.muscle,
            difficulty=excluded.difficulty,
            equipment=excluded.equipment,
            summary=excluded.summary,
            benefits=excluded.benefits,
            how_to=excluded.how_to,
            sets_reps=excluded.sets_reps
    """, (
        exercise_name,
        details.get('muscle', 'Full Body'),
        details.get('difficulty', 'Intermediate'),
        details.get('equipment', 'None'),
        details.get('summary', ''),
        json.dumps(details.get('benefits', [])),
        json.dumps(details.get('how_to', [])),
        details.get('sets_reps', '3 sets × 10 reps')
    ))
    conn.commit()
    conn.close()


# ── USER PROFILE ─────────────────────────

def username_exists(username, exclude_user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=? AND id!=?", (username, exclude_user_id))
    row = c.fetchone()
    conn.close()
    return row is not None


def update_user_profile(user_id, name, email, phone=None, bio=None, fitness_goal=None, first_name=None, last_name=None, username=None):
    conn = get_db()
    c = conn.cursor()
    if username:
        c.execute(
            "UPDATE users SET name=?, email=?, phone=?, bio=?, fitness_goal=?, first_name=?, last_name=?, username=? WHERE id=?",
            (name, email, phone, bio, fitness_goal, first_name, last_name, username, user_id)
        )
    elif first_name is not None and last_name is not None:
        c.execute(
            "UPDATE users SET name=?, email=?, phone=?, bio=?, fitness_goal=?, first_name=?, last_name=? WHERE id=?",
            (name, email, phone, bio, fitness_goal, first_name, last_name, user_id)
        )
    else:
        c.execute(
            "UPDATE users SET name=?, email=?, phone=?, bio=?, fitness_goal=? WHERE id=?",
            (name, email, phone, bio, fitness_goal, user_id)
        )
    conn.commit()
    conn.close()


def update_user_avatar(user_id, avatar_path=None, avatar_data=None, avatar_mime=None):
    """Store an avatar. Either a legacy static path, or raw image bytes
    (avatar_data/avatar_mime) kept in the database for serverless deploys."""
    conn = get_db()
    c = conn.cursor()
    if avatar_data is not None:
        c.execute(
            "UPDATE users SET avatar='db', avatar_data=?, avatar_mime=? WHERE id=?",
            (avatar_data, avatar_mime or 'image/png', user_id)
        )
    else:
        c.execute(
            "UPDATE users SET avatar=?, avatar_data=NULL, avatar_mime=NULL WHERE id=?",
            (avatar_path, user_id)
        )
    conn.commit()
    conn.close()


def email_exists(email, exclude_user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=? AND id!=?", (email, exclude_user_id))
    row = c.fetchone()
    conn.close()
    return row is not None


# ── EMAIL VERIFICATION ────────────────────

def set_verification_token(user_id, token):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET verification_token=? WHERE id=?", (token, user_id))
    conn.commit()
    conn.close()


def get_user_by_verification_token(token):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE verification_token=?", (token,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def verify_user_email(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET is_verified=1, verification_token=NULL WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


# ── WORKOUT TEMPLATES ─────────────────────

def apply_workout_template(user_id, plan):
    """
    Replace the user's entire workout plan + progress with a template.
    History and exercise notes are left untouched.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM workout_plan WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM progress WHERE user_id=?", (user_id,))
    for day, exercises in plan.items():
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


# ── CHAT HISTORY (IronBot) ─────────────────

def create_chat_session(user_id, title='New Chat'):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)", (user_id, title))
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_chat_session(session_id, user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user_id))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_chat_sessions(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT cs.*, COUNT(cm.id) AS message_count
        FROM chat_sessions cs
        LEFT JOIN chat_messages cm ON cm.session_id = cs.id
        WHERE cs.user_id=?
        GROUP BY cs.id
        ORDER BY cs.updated_at DESC
    """, (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_chat_messages(session_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role, content, created_at FROM chat_messages WHERE session_id=? ORDER BY id", (session_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_chat_message(session_id, role, content):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )
    c.execute("UPDATE chat_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))
    conn.commit()
    conn.close()


def update_chat_title(session_id, title):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE chat_sessions SET title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (title, session_id))
    conn.commit()
    conn.close()


def delete_chat_session(session_id, user_id):
    conn = get_db()
    c = conn.cursor()
    # Only delete if the session belongs to this user
    c.execute("SELECT id FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user_id))
    if c.fetchone():
        c.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
        c.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()


# ── ACCOUNT LIFECYCLE (deactivate / delete) ───

def set_account_status(user_id, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET account_status=? WHERE id=?", (status, user_id))
    conn.commit()
    conn.close()


def set_delete_email_code(user_id, code, expiry):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET delete_email_code=?, delete_email_code_expiry=? WHERE id=?",
        (code, expiry.isoformat(sep=' '), user_id)
    )
    conn.commit()
    conn.close()


def clear_delete_email_code(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET delete_email_code=NULL, delete_email_code_expiry=NULL WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


def grant_delete_grace(user_id, reason):
    """Mark the account for permanent deletion with a 30-day grace period."""
    now = datetime.now()
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET account_status='pending_delete', delete_reason=?, "
        "delete_requested_at=?, delete_email_code=NULL, delete_email_code_expiry=NULL WHERE id=?",
        (reason, now.isoformat(sep=' '), user_id)
    )
    conn.commit()
    conn.close()


def set_restore_token(user_id):
    token = secrets_token()
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET restore_token=? WHERE id=?", (token, user_id))
    conn.commit()
    conn.close()
    return token


def restore_account_by_token(token):
    """Restore a deactivated / pending_delete account via its restore token."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE restore_token=? AND account_status!='active'", (token,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    uid = row['id']
    c.execute(
        "UPDATE users SET account_status='active', delete_reason=NULL, delete_requested_at=NULL, restore_token=NULL WHERE id=?",
        (uid,)
    )
    conn.commit()
    conn.close()
    return uid


def reactivate_account(user_id):
    """Called while logged-in: immediately restores the account to active."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE users SET account_status='active', delete_reason=NULL, delete_requested_at=NULL, restore_token=NULL WHERE id=?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def delete_user_data(user_id):
    """Permanently remove a user and everything they own."""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM chat_messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE user_id=?)", (user_id,))
    c.execute("DELETE FROM chat_sessions WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM workout_plan WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM progress WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM history WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM streaks WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM exercise_notes WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


def cleanup_expired_deletions(days=30):
    """Delete accounts whose 30-day grace period has passed."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, delete_requested_at FROM users "
        "WHERE account_status='pending_delete' AND delete_requested_at IS NOT NULL"
    )
    rows = c.fetchall()
    conn.close()
    cutoff = datetime.now() - timedelta(days=days)
    ids = []
    for row in rows:
        ts = row['delete_requested_at']
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
            except ValueError:
                continue
        if isinstance(ts, datetime) and ts <= cutoff:
            ids.append(row['id'])
    for uid in ids:
        delete_user_data(uid)
    return len(ids)


# ── FEEDBACK ──────────────────────────────

def save_feedback(category, message, name=None, email=None):
    """Store a feedback submission from the About page."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO feedback (category, name, email, message) VALUES (?, ?, ?, ?)",
        (category, (name or '').strip(), (email or '').strip(), message.strip())
    )
    conn.commit()
    feedback_id = c.lastrowid
    conn.close()
    return feedback_id


def get_feedback(limit=100, only_unreplied=False):
    """List feedback submissions, newest first."""
    conn = get_db()
    c = conn.cursor()
    sql = "SELECT * FROM feedback"
    if only_unreplied:
        sql += " WHERE status = 'new'"
    sql += " ORDER BY id DESC LIMIT ?"
    rows = c.execute(sql, (limit,)).fetchall()
    conn.close()
    return rows


def get_feedback_by_id(feedback_id):
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT * FROM feedback WHERE id=?", (feedback_id,)).fetchone()
    conn.close()
    return row


def count_unreplied_feedback():
    conn = get_db()
    c = conn.cursor()
    n = c.execute("SELECT COUNT(*) AS n FROM feedback WHERE status='new'").fetchone()['n']
    conn.close()
    return n


def set_feedback_reply(feedback_id, reply_text, status='replied'):
    """Store an admin reply and mark the item handled."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE feedback SET reply=?, status=?, replied_at=CURRENT_TIMESTAMP WHERE id=?",
        (reply_text, status, feedback_id)
    )
    conn.commit()
    conn.close()


def set_feedback_status(feedback_id, status):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE feedback SET status=? WHERE id=?", (status, feedback_id))
    conn.commit()
    conn.close()


def delete_feedback(feedback_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM feedback WHERE id=?", (feedback_id,))
    conn.commit()
    conn.close()


# ── SECURITY: LOCKOUT, AUDIT, 2FA ────────────────────

AUTH_MAX_FAILURES = 5
AUTH_LOCK_MINUTES = 15


def _parse_ts(ts):
    """Return a datetime regardless of whether `ts` is a string or datetime."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None


def auth_locked_seconds(identifier):
    """Return remaining lockout seconds, or 0 if not locked."""
    if not identifier:
        return 0
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT locked_until FROM auth_attempts WHERE identifier=?", (identifier,))
    row = c.fetchone()
    conn.close()
    if not row:
        return 0
    locked_until = _parse_ts(row.get('locked_until') if isinstance(row, dict) else None)
    if locked_until:
        remaining = (locked_until - datetime.utcnow()).total_seconds()
        if remaining > 0:
            return int(remaining)
    return 0


def record_auth_failure(identifier, ip=''):
    """Increment failure count; lock when threshold exceeded. Returns True if now locked."""
    if not identifier:
        return False
    now = datetime.utcnow().isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, failed FROM auth_attempts WHERE identifier=?", (identifier,))
    row = c.fetchone()
    locked = False
    if row:
        failed = (row['failed'] or 0) + 1
        if failed >= AUTH_MAX_FAILURES:
            locked_until = (datetime.utcnow() + timedelta(minutes=AUTH_LOCK_MINUTES)).isoformat()
            locked = True
        else:
            locked_until = None
        c.execute("UPDATE auth_attempts SET failed=?, last_fail=?, locked_until=? WHERE id=?",
                  (failed, now, locked_until, row['id']))
    else:
        c.execute("INSERT INTO auth_attempts (identifier, failed, last_fail, locked_until) VALUES (?, 1, ?, NULL)",
                  (identifier, now))
    conn.commit()
    conn.close()
    return locked


def clear_auth_failures(identifier):
    if not identifier:
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE auth_attempts SET failed=0, locked_until=NULL WHERE identifier=?", (identifier,))
    conn.commit()
    conn.close()


def audit(user_id, email, action, detail='', ip=''):
    """Best-effort audit log — never raises."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO audit_log (user_id, email, action, detail, ip) VALUES (?, ?, ?, ?, ?)",
                  (user_id, email, action, detail, ip))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_totp_secret(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT totp_secret FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return ''
    return row.get('totp_secret') or ''


def set_totp_secret(user_id, secret):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET totp_secret=? WHERE id=?", (secret, user_id))
    conn.commit()
    conn.close()