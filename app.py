import os
import json as json_mod
import secrets
import random
import socket
import time as time_mod
import mimetypes
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from workout import (
    get_all_days, get_exercises_for_day,
    add_exercise, remove_exercise,
    get_progress, mark_complete, reset_day,
    get_summary, calculate_bmi
)
from data import (
    get_history, get_streak, get_note, save_note,
    get_user_by_email, get_user_by_id, get_user_by_username,
    create_user,
    set_reset_token, get_user_by_reset_token, update_password,
    get_ai_exercise_details, save_ai_exercise_details,
    update_user_profile, email_exists, username_exists,
    set_verification_token, get_user_by_verification_token,
    verify_user_email, apply_workout_template,
    get_user_by_google_id, link_google_id, create_google_user,
    create_chat_session, get_chat_session, get_chat_sessions,
    get_chat_messages, add_chat_message, update_chat_title,
    delete_chat_session,
    set_account_status, set_delete_email_code, clear_delete_email_code,
    grant_delete_grace, set_restore_token, restore_account_by_token,
    reactivate_account, delete_user_data, cleanup_expired_deletions,
    save_feedback, get_feedback, get_feedback_by_id, count_unreplied_feedback,
    set_feedback_reply, set_feedback_status, delete_feedback,
    update_user_avatar
)
from authlib.integrations.flask_client import OAuth
from exercises import EXERCISES
from workout_templates import WORKOUT_TEMPLATES
from database import init_db, seed_default_plan, get_db
from groq import Groq

load_dotenv(override=True)

app = Flask(__name__)
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    key_file = os.path.join(os.path.dirname(__file__), '.secret_key')
    if os.path.exists(key_file):
        try:
            secret_key = open(key_file).read().strip()
        except Exception:
            secret_key = ''
    if not secret_key:
        secret_key = secrets.token_hex(32)
        try:
            with open(key_file, 'w') as f:
                f.write(secret_key)
        except Exception:
            # Read-only filesystem on serverless: sessions simply reset per instance.
            pass
app.secret_key = secret_key
app.config['PREFERRED_URL_SCHEME'] = os.environ.get('PREFERRED_URL_SCHEME', 'https' if os.environ.get('VERCEL') else 'http')

# ── SESSION COOKIE SECURITY ──
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_NAME'] = 'irontrack_session'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'true' if os.environ.get('VERCEL') else 'false').lower() == 'true'

# ── PROFILE PHOTO UPLOADS ──
import os as _os
UPLOAD_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'static', 'uploads')
try:
    _os.makedirs(UPLOAD_DIR, exist_ok=True)
except OSError:
    pass
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def _allowed_avatar(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ── SEO ──
SITE_URL = os.environ.get('SITE_URL', '').rstrip('/')

# ── DESIGN SYSTEM — root css/ folder ──
@app.route('/css/<path:filename>')
def css_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'css'), filename)

# ── ADMIN ──
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()}


def is_admin():
    return current_user.is_authenticated and (current_user.email or '').lower() in ADMIN_EMAILS


def avatar_url(user):
    """Return the URL for a user avatar, or None if none is set.
    Supports avatars stored in the DB (serverless) and legacy static files."""
    if not user:
        return None
    if isinstance(user, dict):
        avatar = user.get('avatar') or ''
        uid = user.get('id')
    else:
        avatar = getattr(user, 'avatar', '') or ''
        uid = getattr(user, 'id', 0)
    if avatar == 'db':
        return url_for('avatar', user_id=uid) if uid else None
    if avatar:
        return url_for('static', filename=avatar)
    return None


@app.context_processor
def inject_site_globals():
    base = SITE_URL or request.url_root.rstrip('/')
    return dict(site_base=base, SITE_URL=SITE_URL, now=datetime.now(), is_admin=is_admin(),
                avatar_url=avatar_url)


@app.route('/avatar/<int:user_id>')
def avatar(user_id):
    """Serve a user's avatar from the database."""
    user_dict = get_user_by_id(int(user_id))
    if not user_dict or not user_dict.get('avatar_data'):
        return ('', 404)
    return Response(bytes(user_dict['avatar_data']),
                    mimetype=user_dict.get('avatar_mime') or 'image/png')

# ── MAIL ──
app.config['MAIL_SERVER']        = 'smtp.gmail.com'
app.config['MAIL_PORT']          = 587
app.config['MAIL_USE_TLS']       = True
app.config['MAIL_USERNAME']      = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD']      = os.environ.get('MAIL_PASSWORD', '').replace(' ', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')
MAIL_ENABLED = bool(app.config['MAIL_USERNAME'] and app.config['MAIL_PASSWORD'])
mail = Mail(app) if MAIL_ENABLED else None

# ── RATE LIMITER ──
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")

# ── SECURITY HEADERS ──
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if SITE_URL.startswith('https'):
        app.config['SESSION_COOKIE_SECURE'] = True
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def _mail_send(msg, tries=3):
    """Send with a short retry loop — absorbs transient DNS/connection blips."""
    for attempt in range(tries):
        try:
            mail.send(msg)
            return
        except OSError:
            if attempt == tries - 1:
                raise
            time_mod.sleep(1 + attempt)


# ── GOOGLE OAUTH ──
oauth = OAuth(app)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_OAUTH_CONFIGURED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
if GOOGLE_OAUTH_CONFIGURED:
    oauth.register(
        name='google',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )


def send_verification_email(email, name, token):
    """Send an account verification email. Raises on failure."""
    if not MAIL_ENABLED:
        raise RuntimeError('Mail not configured. Set MAIL_USERNAME and MAIL_PASSWORD in .env')
    verify_url = url_for('verify_email', token=token, _external=True)
    msg = Message(
        subject='IronTrack — Verify Your Email',
        recipients=[email],
        html=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0a0a0a;color:#f0f0f0;border-radius:12px;overflow:hidden;">
            <div style="background:#c8ff00;padding:24px;text-align:center;">
                <h1 style="font-family:monospace;font-size:28px;color:#000;letter-spacing:4px;margin:0;">IRONTRACK</h1>
            </div>
            <div style="padding:32px;">
                <h2 style="color:#c8ff00;margin-bottom:16px;">Welcome, {name}!</h2>
                <p style="color:#aaa;margin-bottom:24px;">Confirm your email address to fully activate your IronTrack account.</p>
                <a href="{verify_url}" style="display:inline-block;background:#c8ff00;color:#000;padding:14px 32px;border-radius:8px;font-weight:700;text-decoration:none;">Verify Email Address</a>
                <p style="color:#555;font-size:12px;margin-top:24px;">If you didn't create this account, you can safely ignore this email.</p>
            </div>
        </div>"""
    )
    _mail_send(msg)

# ── ACCOUNT LIFECYCLE ──────────────────────

DELETE_GRACE_DAYS = 30
DELETE_CODE_TTL_MINUTES = 10

DELETE_REASONS = [
    "Using another fitness or tracking app",
    "The app doesn't meet my needs",
    "Too many notifications",
    "Privacy concerns",
    "I'm creating a new account",
    "Temporary — I'll come back later",
    "Something else",
]


def account_days_left(user_dict):
    """Days remaining in the 30-day deletion grace window (1–30)."""
    try:
        when = user_dict.get('delete_requested_at')
        if not when:
            return DELETE_GRACE_DAYS
        requested = datetime.fromisoformat(str(when).replace('Z', '').strip())
        elapsed = (datetime.now() - requested).days
        return max(1, min(DELETE_GRACE_DAYS, DELETE_GRACE_DAYS - elapsed))
    except Exception:
        return DELETE_GRACE_DAYS


def send_delete_code_email(email, name, code):
    """Email a 6-digit verification code before allowing account deletion."""
    if not MAIL_ENABLED:
        raise RuntimeError('Mail not configured. Set MAIL_USERNAME and MAIL_PASSWORD in .env')
    msg = Message(
        subject='IronTrack — Verify Account Deletion',
        recipients=[email],
        html=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0a0a0a;color:#f0f0f0;border-radius:12px;overflow:hidden;">
            <div style="background:#c8ff00;padding:24px;text-align:center;">
                <h1 style="font-family:monospace;font-size:28px;color:#000;letter-spacing:4px;margin:0;">IRONTRACK</h1>
            </div>
            <div style="padding:32px;">
                <h2 style="color:#c8ff00;margin-bottom:16px;">Confirm account deletion, {name}</h2>
                <p style="color:#aaa;margin-bottom:24px;">We received a request to delete your IronTrack account. Enter this code to continue:</p>
                <div style="background:#141414;border:1px solid #2a2a2a;border-radius:12px;padding:20px 24px;text-align:center;font-size:30px;letter-spacing:12px;font-weight:800;color:#c8ff00;margin-bottom:24px;">{code}</div>
                <p style="color:#555;font-size:12px;">The code expires in 10 minutes. If you didn't request this, you can safely ignore this email.</p>
            </div>
        </div>"""
    )
    _mail_send(msg)


def send_deletion_confirmation_email(email, name, days, restore_url):
    """Sent once deletion is confirmed. Includes a restore link for the grace period."""
    if not MAIL_ENABLED:
        raise RuntimeError('Mail not configured. Set MAIL_USERNAME and MAIL_PASSWORD in .env')
    msg = Message(
        subject='IronTrack — We will delete your account in 30 days',
        recipients=[email],
        html=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0a0a0a;color:#f0f0f0;border-radius:12px;overflow:hidden;">
            <div style="background:#c8ff00;padding:24px;text-align:center;">
                <h1 style="font-family:monospace;font-size:28px;color:#000;letter-spacing:4px;margin:0;">IRONTRACK</h1>
            </div>
            <div style="padding:32px;">
                <h2 style="color:#c8ff00;margin-bottom:16px;">Your account is scheduled for deletion</h2>
                <p style="color:#aaa;margin-bottom:12px;">Hi {name}, your IronTrack account and all your data will be <b style="color:#f0f0f0;">permanently deleted after {days} days</b>.</p>
                <p style="color:#aaa;margin-bottom:24px;">Changed your mind? You can restore your account any time before that date.</p>
                <a href="{restore_url}" style="display:inline-block;background:#c8ff00;color:#000;padding:14px 32px;border-radius:8px;font-weight:700;text-decoration:none;">Restore My Account</a>
                <p style="color:#555;font-size:12px;margin-top:24px;">If you didn't request this, please secure your email account or contact support.</p>
            </div>
        </div>"""
    )
    _mail_send(msg)


def send_deactivation_email(email, name, reactivate_url):
    """Sent when an account is temporarily deactivated."""
    if not MAIL_ENABLED:
        raise RuntimeError('Mail not configured. Set MAIL_USERNAME and MAIL_PASSWORD in .env')
    msg = Message(
        subject='IronTrack — Account deactivated',
        recipients=[email],
        html=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0a0a0a;color:#f0f0f0;border-radius:12px;overflow:hidden;">
            <div style="background:#c8ff00;padding:24px;text-align:center;">
                <h1 style="font-family:monospace;font-size:28px;color:#000;letter-spacing:4px;margin:0;">IRONTRACK</h1>
            </div>
            <div style="padding:32px;">
                <h2 style="color:#c8ff00;margin-bottom:16px;">Your account is deactivated, {name}</h2>
                <p style="color:#aaa;margin-bottom:24px;">There's more to come. Come back any time to pick up right where you left off — your workouts and progress are safe.</p>
                <a href="{reactivate_url}" style="display:inline-block;background:#c8ff00;color:#000;padding:14px 32px;border-radius:8px;font-weight:700;text-decoration:none;">Reactivate Account</a>
                <p style="color:#555;font-size:12px;margin-top:24px;">If you didn't request this, you can safely ignore this email.</p>
            </div>
        </div>"""
    )
    _mail_send(msg)


def send_feedback_reply_email(feedback_email, to_name, original_message, reply_text):
    """Email an admin reply back to someone who left feedback. Raises on failure."""
    msg = Message(
        subject='IronTrack — Re: Your Feedback',
        recipients=[feedback_email],
        html=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0a0a0a;color:#f0f0f0;border-radius:12px;overflow:hidden;">
            <div style="background:#c8ff00;padding:24px;text-align:center;">
                <h1 style="font-family:monospace;font-size:28px;color:#000;letter-spacing:4px;margin:0;">IRONTRACK</h1>
            </div>
            <div style="padding:32px;">
                <h2 style="color:#c8ff00;margin:0 0 16px;">Hi {to_name},</h2>
                <div style="background:#1a1a1a;border-left:3px solid #555;padding:14px 18px;margin-bottom:20px;color:#bbb;font-size:13px;font-style:italic;">
                    "Your feedback: {original_message}"
                </div>
                <p style="margin:0 0 16px;color:#eee;line-height:1.6;">{reply_text}</p>
                <p style="color:#555;font-size:12px;margin-bottom:0;">Thanks for helping make IronTrack better.<br>The IronTrack Team</p>
            </div>
        </div>"""
    )
    _mail_send(msg)


# ── LOGIN MANAGER ──
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = ''
login_manager.remember_cookie_duration = timedelta(days=90)

class User(UserMixin):
    def __init__(self, user_dict):
        self.id          = user_dict['id']
        self.name        = user_dict['name']
        self.first_name  = user_dict.get('first_name') or (user_dict['name'].split()[0] if user_dict['name'] else '')
        self.last_name   = user_dict.get('last_name') or (user_dict['name'].split(None, 1)[1] if ' ' in user_dict['name'] else '')
        self.email       = user_dict['email']
        self.username    = user_dict.get('username', '')
        self.avatar      = user_dict.get('avatar') or ''
        self.avatar_data = user_dict.get('avatar_data')
        self.avatar_mime = user_dict.get('avatar_mime') or 'image/png'
        self.is_verified = bool(user_dict.get('is_verified', 1))
        self.account_status = user_dict.get('account_status') or 'active'

@login_manager.user_loader
def load_user(user_id):
    user_dict = get_user_by_id(int(user_id))
    return User(user_dict) if user_dict else None

with app.app_context():
    from database import init_db, init_ai_exercise_details_table, init_feedback_table
    try:
        init_db()
    except Exception as e:
        print(f"[Startup] init_db skipped: {e}")
    try:
        init_ai_exercise_details_table()
    except Exception as e:
        print(f"[Startup] init_ai_exercise_details_table skipped: {e}")
    try:
        init_feedback_table()
    except Exception as e:
        print(f"[Startup] init_feedback_table skipped: {e}")
    # Purge accounts whose 30-day deletion grace period has already passed
    try:
        expired = cleanup_expired_deletions(days=DELETE_GRACE_DAYS)
        if expired:
            print(f"[Account Lifecycle] Permanently deleted {expired} expired account(s).")
    except Exception as e:
        print(f"[Account Lifecycle] Cleanup skipped: {e}")

try:
    groq_client = Groq()
except Exception:
    groq_client = None



# AUTH ROUTES


# Deactivated / pending-deletion accounts can only reach the account-status page
@app.before_request
def gate_inactive_accounts():
    if current_user.is_authenticated:
        status = getattr(current_user, 'account_status', 'active')
        if status in ('deactivated', 'pending_delete'):
            allowed = ('account_status', 'account_reactivate', 'account_restore_token', 'logout', 'static')
            if request.endpoint not in allowed:
                return redirect(url_for('account_status'))


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        name       = f"{first_name} {last_name}".strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')
        username = request.form.get('username', '').strip().lower()
        if not username:
            username = email.split('@')[0]
        if not first_name or not email or not password:
            flash('All fields are required.')
            return render_template('register.html')
        if password != confirm:
            flash('Passwords do not match.')
            return render_template('register.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.')
            return render_template('register.html')
        if get_user_by_email(email):
            flash('An account with this email already exists.')
            return render_template('register.html')
        if get_user_by_username(username):
            flash('This username is already taken.')
            return render_template('register.html')
        password_hash = generate_password_hash(password)
        verification_token = secrets.token_urlsafe(32)
        user_id = create_user(name, email, password_hash, verification_token, first_name=first_name, last_name=last_name, username=username)
        phone = request.form.get('phone', '').strip()
        if phone:
            update_user_profile(user_id, name, email, phone=phone, first_name=first_name, last_name=last_name, username=username)
        seed_default_plan(user_id)

        user = User(get_user_by_id(user_id))
        login_user(user)
        session.pop('guest', None)
        try:
            send_verification_email(email, first_name, verification_token)
            flash('Account created! Check your email to verify your account.')
        except Exception as e:
            flash(f'Account created. Could not send verification email: {e}')
        return redirect(url_for('home'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        login_id = request.form.get('login_id', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        user_dict = get_user_by_email(login_id)
        if not user_dict:
            user_dict = get_user_by_username(login_id)
        if not user_dict or not check_password_hash(user_dict['password_hash'], password):
            flash('Invalid email/username or password.')
            return render_template('login.html')
        login_user(User(user_dict), remember=remember)
        session.pop('guest', None)
        # Deactivated / pending deletion accounts land on the account-status page
        if user_dict.get('account_status') in ('deactivated', 'pending_delete'):
            return redirect(url_for('account_status'))
        return redirect(request.args.get('next') or url_for('home'))
    return render_template('login.html')


@app.route('/login/google')
def google_login():
    if not GOOGLE_OAUTH_CONFIGURED:
        flash('Google Sign-In is not configured yet. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env')
        return redirect(url_for('login'))
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    # Callback URL. IMPORTANT: it MUST use the exact same origin the user is
    # browsing on. The OAuth `state` is stored in a session cookie scoped to
    # that origin, so if the browser is on 127.0.0.1:5000 the callback must
    # also be 127.0.0.1:5000 (and vice versa for localhost) — otherwise the
    # cookie isn't sent back and you get "state not equal" CSRF errors.
    scheme = app.config.get('PREFERRED_URL_SCHEME', 'http')
    redirect_uri = f"{scheme}://{request.host}/login/google/authorized"

    # Print the exact URI Google must send the user back to.
    # Both of these must be registered as Authorized redirect URIs in
    # Google Cloud Console: http://localhost:5000/... and http://127.0.0.1:5000/...
    print(f"[Google OAuth] redirect_uri = {redirect_uri}")

    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/login/google/authorized')
def google_authorized():
    if not GOOGLE_OAUTH_CONFIGURED:
        flash('Google Sign-In is not configured yet. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env')
        return redirect(url_for('login'))
    try:
        token = oauth.google.authorize_access_token()
    except Exception as e:
        flash(f'Google sign-in failed: {str(e)}')
        return redirect(url_for('login'))
    userinfo = token.get('userinfo')
    if not userinfo:
        userinfo = oauth.google.parse_id_token(token)
    if not userinfo:
        flash('Could not retrieve your Google profile.')
        return redirect(url_for('login'))

    email    = (userinfo.get('email') or '').lower()
    google_id = str(userinfo.get('sub'))
    name     = userinfo.get('name') or email.split('@')[0] or 'IronTrack User'
    first_name = userinfo.get('given_name') or name.split()[0] if name else 'Iron'
    last_name  = userinfo.get('family_name') or (name.split(None, 1)[1] if ' ' in name else '')

    # 1. Existing user already linked to this Google account
    user_dict = get_user_by_google_id(google_id)
    if user_dict:
        login_user(User(user_dict))
        session.pop('guest', None)
        if user_dict.get('account_status') in ('deactivated', 'pending_delete'):
            return redirect(url_for('account_status'))
        return redirect(request.args.get('next') or url_for('home'))

    # 2. Existing user with the same email → link the Google account
    user_dict = get_user_by_email(email)
    if user_dict:
        link_google_id(user_dict['id'], google_id)
        login_user(User(user_dict))
        session.pop('guest', None)
        flash('Google account linked to your existing login.')
        if user_dict.get('account_status') in ('deactivated', 'pending_delete'):
            return redirect(url_for('account_status'))
        return redirect(request.args.get('next') or url_for('home'))

    # 3. Brand new user
    user_id = create_google_user(name, email, google_id,
                                 username=email.split('@')[0] if email else 'user',
                                 first_name=first_name, last_name=last_name)
    seed_default_plan(user_id)
    user_dict = get_user_by_id(user_id)
    login_user(User(user_dict))
    session.pop('guest', None)
    flash('Welcome! Your account was created with Google.')
    return redirect(url_for('home'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('guest', None)
    return redirect(url_for('login'))


@app.route('/explore')
def explore():
    """Let visitors browse the app without signing up."""
    session['guest'] = True
    return redirect(url_for('home'))


# ── SEO: robots.txt + sitemap.xml ──

# Publicly crawlable pages (relative path, change freq, priority)
SITEMAP_PAGES = [
    ('/', 'weekly', '1.0'),
    ('/workout', 'weekly', '0.9'),
    ('/templates', 'weekly', '0.8'),
    ('/bmi', 'weekly', '0.8'),
    ('/assistant', 'weekly', '0.7'),
    ('/about', 'monthly', '0.5'),
]


@app.route('/robots.txt')
def robots_txt():
    base = SITE_URL or request.url_root.rstrip('/')
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
        "Disallow: /forgot-password\n"
        "Disallow: /reset-password/\n"
        "Disallow: /verify-email/\n"
        "Disallow: /logout\n"
        "Disallow: /profile\n"
        "Disallow: /account\n"
        "Disallow: /api/\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return Response(body, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap():
    base = SITE_URL or request.url_root.rstrip('/')
    entries = [(f"{base}{path}", freq, pri) for path, freq, pri in SITEMAP_PAGES]
    for name in EXERCISES:
        entries.append((f"{base}/exercise/{name.replace(' ', '%20')}", 'monthly', '0.6'))
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for loc, freq, pri in entries:
        xml.append(f'  <url><loc>{loc}</loc><changefreq>{freq}</changefreq><priority>{pri}</priority></url>')
    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')


@app.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per minute")
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user_dict = get_user_by_email(email)
        if user_dict:
            token = secrets.token_urlsafe(32)
            expiry = datetime.utcnow() + timedelta(hours=1)
            set_reset_token(email, token, expiry)
            reset_url = url_for('reset_password', token=token, _external=True)
            try:
                msg = Message(
                    subject='IronTrack — Password Reset',
                    recipients=[email],
                    html=f"""
                    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#0a0a0a;color:#f0f0f0;border-radius:12px;overflow:hidden;">
                        <div style="background:#c8ff00;padding:24px;text-align:center;">
                            <h1 style="font-family:monospace;font-size:28px;color:#000;letter-spacing:4px;margin:0;">IRONTRACK</h1>
                        </div>
                        <div style="padding:32px;">
                            <h2 style="color:#c8ff00;margin-bottom:16px;">Reset Your Password</h2>
                            <p style="color:#aaa;margin-bottom:24px;">Click the button below to reset your password. This link expires in 1 hour.</p>
                            <a href="{reset_url}" style="display:inline-block;background:#c8ff00;color:#000;padding:14px 32px;border-radius:8px;font-weight:700;text-decoration:none;">Reset Password</a>
                            <p style="color:#555;font-size:12px;margin-top:24px;">If you didn't request this, ignore this email.</p>
                        </div>
                    </div>"""
                )
                _mail_send(msg)
            except Exception as e:
                flash(f'Email error: {str(e)}')
                return render_template('forgot_password.html')
        flash('If that email exists, a reset link has been sent.')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user_dict = get_user_by_reset_token(token)
    if not user_dict:
        flash('Invalid or expired reset link.')
        return redirect(url_for('forgot_password'))
    try:
        expiry = datetime.fromisoformat(str(user_dict['reset_token_expiry']))
    except (ValueError, TypeError):
        flash('Invalid or expired reset link.')
        return redirect(url_for('forgot_password'))
    if datetime.utcnow() > expiry:
        flash('This reset link has expired.')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')
        if len(password) < 6:
            flash('Password must be at least 6 characters.')
            return render_template('reset_password.html', token=token)
        if password != confirm:
            flash('Passwords do not match.')
            return render_template('reset_password.html', token=token)
        update_password(user_dict['id'], generate_password_hash(password))
        flash('Password updated. Please log in.')
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)


@app.route('/verify-email/<token>')
def verify_email(token):
    user_dict = get_user_by_verification_token(token)
    if not user_dict:
        flash('Invalid or expired verification link.')
        return redirect(url_for('login'))

    verify_user_email(user_dict['id'])
    flash('Email verified successfully! 🎉')

    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    return redirect(url_for('login'))


@app.route('/resend-verification', methods=['POST'])
@login_required
def resend_verification():
    user_dict = get_user_by_id(current_user.id)

    if user_dict['is_verified']:
        flash('Your email is already verified.')
        return redirect(url_for('profile'))

    token = secrets.token_urlsafe(32)
    set_verification_token(current_user.id, token)

    try:
        send_verification_email(current_user.email, current_user.name, token)
        flash('Verification email sent — check your inbox.')
    except Exception as e:
        flash(f'Could not send email: {str(e)}')

    return redirect(url_for('profile'))



# HELPER — get current user id (real or guest)


def get_uid():
    """Return current user id, or None for guests."""
    if current_user.is_authenticated:
        return current_user.id
    return None

def is_guest():
    return not current_user.is_authenticated and session.get('guest')

def require_auth_or_guest():
    """Redirect to login if neither logged in nor exploring as guest."""
    if not current_user.is_authenticated and not session.get('guest'):
        return redirect(url_for('login'))
    return None



# MAIN ROUTES


@app.route('/')
def home():
    redir = require_auth_or_guest()
    if redir: return redir
    streak = get_streak(get_uid()) if get_uid() else 0
    active_day_index = streak % 9
    return render_template('index.html', streak=streak, active_day_index=active_day_index,
                           guest=is_guest())


@app.route('/about')
def about():
    return render_template('about.html', fb=None)


@app.route('/feedback', methods=['POST'])
@limiter.limit("3 per minute")
def feedback():
    message = request.form.get('message', '').strip()
    if not message:
        flash('Please write a short message before sending.')
        return render_template('about.html', fb=request.form)
    category = request.form.get('category', 'General').strip() or 'General'
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    save_feedback(category, message, name=name, email=email)
    flash('Thanks for your feedback — it helps make IronTrack better!')
    return redirect(url_for('about'))


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return wrapper


@app.route('/admin/feedback')
@admin_required
def admin_feedback():
    only_unreplied = request.args.get('f') == 'unreplied'
    all_items = get_feedback(limit=500)
    items = get_feedback(limit=500, only_unreplied=only_unreplied)
    return render_template('admin_feedback.html', items=items,
                           only_unreplied=only_unreplied,
                           total=len(all_items),
                           unreplied=count_unreplied_feedback(),
                           mail_enabled=MAIL_ENABLED)


def _admin_filter_back():
    f = request.form.get('filter')
    if f == 'unreplied':
        return url_for('admin_feedback', f='unreplied')
    return url_for('admin_feedback')


@app.route('/admin/feedback/<int:feedback_id>/reply', methods=['POST'])
@admin_required
def admin_feedback_reply(feedback_id):
    item = get_feedback_by_id(feedback_id)
    if not item:
        flash('Feedback entry not found.')
        return redirect(url_for('admin_feedback'))
    reply_text = request.form.get('reply', '').strip()
    if not reply_text:
        flash('Write a reply first.')
        return redirect(_admin_filter_back())

    set_feedback_reply(feedback_id, reply_text, status='replied')

    emailed = False
    if item['email'] and MAIL_ENABLED:
        try:
            send_feedback_reply_email(item['email'], item['name'] or 'there', item['message'], reply_text)
            emailed = True
        except (socket.gaierror, socket.herror):
            flash(f'Reply saved, but the email could not be delivered — {item["email"]} may not be a real address.', 'error')
        except Exception:
            flash(f'Reply saved, but the email could not be sent (server or network issue).', 'error')

    dest = item['email'] if item['email'] else 'a visitor (no email given)'
    flash(f'Reply saved{" and emailed" if emailed else ""} to {dest}.')
    return redirect(_admin_filter_back())


@app.route('/admin/feedback/<int:feedback_id>/mark', methods=['POST'])
@admin_required
def admin_feedback_mark(feedback_id):
    status = request.form.get('status', 'reviewed')
    set_feedback_status(feedback_id, status if status in ('reviewed', 'new', 'replied') else 'reviewed')
    flash('Feedback updated.')
    return redirect(_admin_filter_back())


@app.route('/admin/feedback/<int:feedback_id>/delete', methods=['POST'])
@admin_required
def admin_feedback_delete(feedback_id):
    delete_feedback(feedback_id)
    flash('Feedback entry deleted.')
    return redirect(_admin_filter_back())


@app.route('/workout')
def workout():
    redir = require_auth_or_guest()
    if redir: return redir
    if is_guest():
        # Show demo data for guests
        demo_days = ["Day 1 (Chest)", "Day 2 (Legs)", "Day 3 (Back)"]
        demo_exercises = {
            "Push-ups": False, "Bench Press": False, "Chest Fly": False
        }
        return render_template('workout.html', days=demo_days,
                               selected_day="Day 1 (Chest)",
                               exercises=demo_exercises, notes={}, guest=True)
    days = get_all_days(current_user.id)
    selected_day = request.args.get('day', days[0] if days else '')
    exercises = get_progress(current_user.id).get(selected_day, {})
    notes = {ex: get_note(current_user.id, ex) for ex in exercises}
    return render_template('workout.html', days=days, selected_day=selected_day,
                           exercises=exercises, notes=notes, guest=False)


@app.route('/mark_complete', methods=['POST'])
@login_required
def mark_complete_route():
    day = request.form.get('day')
    exercise = request.form.get('exercise')
    if not day or not exercise:
        flash('Missing day or exercise.')
        return redirect(url_for('workout'))
    mark_complete(current_user.id, day, exercise)
    return redirect(url_for('workout', day=day))


@app.route('/add_exercise', methods=['POST'])
@login_required
def add_exercise_route():
    day = request.form.get('day')
    exercise = request.form.get('exercise', '').strip()
    if exercise:
        if not add_exercise(current_user.id, day, exercise):
            flash('Exercise already exists or invalid day.')
    return redirect(url_for('workout', day=day))


@app.route('/remove_exercise', methods=['POST'])
@login_required
def remove_exercise_route():
    day = request.form.get('day')
    exercise = request.form.get('exercise')
    if not day or not exercise:
        flash('Missing day or exercise.')
        return redirect(url_for('workout'))
    remove_exercise(current_user.id, day, exercise)
    return redirect(url_for('workout', day=day))


@app.route('/reset_day', methods=['POST'])
@login_required
def reset_day_route():
    day = request.form.get('day')
    if not day:
        flash('Missing day.')
        return redirect(url_for('workout'))
    reset_day(current_user.id, day)
    return redirect(url_for('workout', day=day))


@app.route('/save_note', methods=['POST'])
@login_required
def save_note_route():
    exercise = request.form.get('exercise')
    note = request.form.get('note', '').strip()
    day = request.form.get('day')
    if not exercise or not day:
        flash('Missing exercise or day.')
        return redirect(url_for('workout'))
    save_note(current_user.id, exercise, note)
    return redirect(url_for('workout', day=day))


@app.route('/add_day', methods=['POST'])
@login_required
def add_day():
    day_name = request.form.get('day_name', '').strip()
    if day_name:
        from data import save_workout_exercise, save_progress
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM workout_plan WHERE user_id=? AND day=?",
                  (current_user.id, day_name))
        exists = c.fetchone()[0] > 0
        conn.close()
        if not exists:
            save_workout_exercise(current_user.id, day_name, 'Rest / Stretching')
            save_progress(current_user.id, day_name, 'Rest / Stretching', False)
        else:
            flash('Day already exists.')
    return redirect(url_for('workout'))


@app.route('/templates')
def templates_page():
    redir = require_auth_or_guest()
    if redir: return redir
    return render_template('workout_templates.html',
                           templates=WORKOUT_TEMPLATES, guest=is_guest())


@app.route('/templates/apply/<template_id>', methods=['POST'])
@login_required
def apply_template(template_id):
    template = WORKOUT_TEMPLATES.get(template_id)
    if not template:
        flash('Template not found.')
        return redirect(url_for('templates_page'))

    apply_workout_template(current_user.id, template['plan'])
    flash(f"\"{template['name']}\" applied — your workout plan has been updated.")
    return redirect(url_for('workout'))


@app.route('/bmi', methods=['GET', 'POST'])
def bmi():
    redir = require_auth_or_guest()
    if redir: return redir
    result = None
    if request.method == 'POST':
        try:
            weight = float(request.form.get('weight'))
            height = float(request.form.get('height'))
            bmi_value, category = calculate_bmi(weight, height)
            result = {'bmi': bmi_value, 'category': category}
        except (ValueError, TypeError):
            flash('Please enter valid numbers.')
    return render_template('bmi.html', result=result, guest=is_guest())


@app.route('/summary')
def summary():
    redir = require_auth_or_guest()
    if redir: return redir
    if is_guest():
        stats = {"total": 25, "completed": 0, "percent": 0,
                 "days": {"Day 1 (Chest)": {"total": 3, "completed": 0, "percent": 0}}}
        return render_template('summary.html', stats=stats, streak=0, guest=True)
    stats = get_summary(current_user.id)
    streak = get_streak(current_user.id)
    return render_template('summary.html', stats=stats, streak=streak, guest=False)


@app.route('/history')
def history():
    redir = require_auth_or_guest()
    if redir: return redir
    if is_guest():
        return render_template('history.html', logs=[], guest=True)
    logs = get_history(current_user.id, limit=100)
    return render_template('history.html', logs=logs, guest=False)


@app.route('/exercise/<name>')
def exercise_detail(name):
    redir = require_auth_or_guest()
    if redir: return redir
    note = get_note(current_user.id, name) if get_uid() else ""

    # Check hardcoded exercises first
    if name in EXERCISES:
        return render_template('exercise.html', name=name, ex=EXERCISES[name],
                               note=note, guest=is_guest(), ai_generated=False)

    # Check AI generated details in database
    ai_details = get_ai_exercise_details(name)
    if ai_details:
        return render_template('exercise.html', name=name, ex=ai_details,
                               note=note, guest=is_guest(), ai_generated=True)

    # No details yet — show generation page
    return render_template('exercise_generate.html', name=name,
                           note=note, guest=is_guest())


@app.route('/assistant')
def assistant():
    redir = require_auth_or_guest()
    if redir: return redir
    sessions = []
    if current_user.is_authenticated:
        sessions = get_chat_sessions(current_user.id)
    return render_template('assistant.html', guest=is_guest(), chat_sessions=sessions)


# ── Chat history API ───────────────────────

def _auth_user_id():
    """Return the current user id if they are logged in (not a guest), else None."""
    if current_user.is_authenticated:
        return current_user.id
    return None


@app.route('/api/chat/sessions')
def api_chat_sessions():
    uid = _auth_user_id()
    if uid is None:
        return jsonify([])
    return jsonify(get_chat_sessions(uid))


@app.route('/api/chat/sessions', methods=['POST'])
def api_chat_create_session():
    uid = _auth_user_id()
    if uid is None:
        return jsonify({'error': 'Not authorized'}), 401
    session_id = create_chat_session(uid)
    return jsonify({'id': session_id, 'title': 'New Chat'})


@app.route('/api/chat/sessions/<int:session_id>')
def api_chat_session(session_id):
    uid = _auth_user_id()
    if uid is None:
        return jsonify({'error': 'Not authorized'}), 401
    session = get_chat_session(session_id, uid)
    if not session:
        return jsonify({'error': 'Not found'}), 404
    messages = get_chat_messages(session_id)
    return jsonify({'session': session, 'messages': messages})


@app.route('/api/chat/sessions/<int:session_id>', methods=['DELETE'])
def api_chat_delete_session(session_id):
    uid = _auth_user_id()
    if uid is None:
        return jsonify({'error': 'Not authorized'}), 401
    delete_chat_session(session_id, uid)
    return jsonify({'ok': True})


@app.route('/assistant/chat', methods=['POST'])
def assistant_chat():
    if not current_user.is_authenticated and not session.get('guest'):
        return jsonify({'error': 'Not authorized'})
    data = request.get_json()
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Empty message'})
    if not groq_client:
        return jsonify({'error': 'AI service not configured. Set GROQ_API_KEY in .env'})

    # Resolve / create a session for logged-in users so history persists
    session_id = None
    if current_user.is_authenticated:
        session_id = data.get('session_id')
        if session_id:
            session_id = int(session_id)
            s = get_chat_session(session_id, current_user.id)
            if not s:
                session_id = None
        if not session_id:
            session_id = create_chat_session(current_user.id)
        sess = get_chat_session(session_id, current_user.id)
        if sess and sess['title'] == 'New Chat':
            update_chat_title(session_id, user_message[:48] or 'New Chat')
        add_chat_message(session_id, 'user', user_message)

    try:
        prompt = """You are IronBot, a friendly, knowledgeable fitness coach inside IronTrack. You are an expert assistant in the style of Gemini and ChatGPT: helpful, conversational, and genuinely useful.

Style and tone:
- Talk like a helpful, encouraging human coach: warm, clear and concise, not stiff or robotic.
- Write natural, flowing answers that are easy to read and answer the question directly.
- Use Markdown lightly: short paragraphs, and use bullet points or numbered steps when they make things clearer. Avoid overusing headers and bold.
- Match the user energy and use the same language they write in.
- Be honest about uncertainty. If something depends on the person, say so and give ranges or options.

Coverage:
- Workouts, exercises, form and technique, muscle building, fat loss, cardio, strength, stretching and mobility, rest and recovery, nutrition and diet, supplements (common ones only), motivation, and goal setting.
- For anything a beginner asks, assume they are new and keep it accessible.

Guardrails:
- Never give medical diagnosis or treatment. For injuries, chronic conditions, pregnancy, or serious pain, encourage seeing a doctor or physical therapist.
- If the question is not fitness-related, gently redirect: say you specialize in fitness and invite a workout question.
- Keep answers reasonably brief: informative but not bloated. A short paragraph plus a few bullet points is usually ideal."""
        response = groq_client.chat.completions.create(
            model='openai/gpt-oss-120b',
            messages=[
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': user_message}
            ],
            temperature=0.7, max_tokens=1000
        )
        reply = response.choices[0].message.content

        if current_user.is_authenticated:
            add_chat_message(session_id, 'assistant', reply)

        return jsonify({'reply': reply, 'session_id': session_id})
    except Exception as e:
        if current_user.is_authenticated:
            return jsonify({'error': str(e), 'session_id': session_id})
        return jsonify({'error': str(e)})


@app.route('/generate_workout', methods=['POST'])
@login_required
def generate_workout():
    data = request.get_json()
    day = data.get('day', '')
    level = data.get('level', 'intermediate')
    if not day:
        return jsonify({'error': 'No day specified'})
    if not groq_client:
        return jsonify({'error': 'AI service not configured. Set GROQ_API_KEY in .env'})
    try:
        response = groq_client.chat.completions.create(
            model='openai/gpt-oss-120b',
            messages=[
                {'role': 'system', 'content': 'You are a fitness coach. Respond ONLY with a valid JSON array of exercise name strings. No explanation, no markdown, no code fences.'},
                {'role': 'user', 'content': f'Generate 4 exercises for {day} at {level} level. Return only a JSON array.'}
            ],
            temperature=0.7, max_tokens=200
        )
        text = response.choices[0].message.content.strip()
        text = text.replace('```json', '').replace('```', '').strip()
        exercises = json_mod.loads(text)
        return jsonify({'exercises': exercises})
    except Exception as e:
        return jsonify({'error': str(e)})




# REACT ANALYTICS API


@app.route('/api/summary-data')
def api_summary_data():
    redir = require_auth_or_guest()
    if redir:
        return jsonify({'error': 'Not authorized'}), 401
    if is_guest():
        return jsonify({
            'stats': {"total": 25, "completed": 0, "percent": 0,
                      "days": {"Day 1 (Chest)": {"total": 3, "completed": 0, "percent": 0}}},
            'streak': 0
        })
    stats = get_summary(current_user.id)
    streak = get_streak(current_user.id)
    return jsonify({'stats': stats, 'streak': streak})



# AI EXERCISE DETAIL GENERATOR


@app.route('/generate_exercise_details/<name>', methods=['POST'])
def generate_exercise_details(name):
    if not current_user.is_authenticated and not session.get('guest'):
        return jsonify({'error': 'Not authorized'})
    if not groq_client:
        return jsonify({'error': 'AI service not configured. Set GROQ_API_KEY in .env'})
    try:
        response = groq_client.chat.completions.create(
            model='openai/gpt-oss-120b',
            messages=[
                {'role': 'system', 'content': '''You are a professional fitness coach. When given an exercise name, respond ONLY with a valid JSON object with exactly these fields:
{
  "muscle": "primary muscle groups targeted",
  "difficulty": "Beginner or Intermediate or Advanced",
  "equipment": "equipment needed",
  "summary": "2-3 sentence description of the exercise",
  "benefits": ["benefit 1", "benefit 2", "benefit 3", "benefit 4", "benefit 5"],
  "how_to": ["step 1", "step 2", "step 3", "step 4", "step 5", "step 6"],
  "sets_reps": "e.g. 3 sets x 10-12 reps",
  "image": "A direct Unsplash image URL for this exercise (e.g. https://images.unsplash.com/photo-XXXXX?w=800&q=80). Pick a real photo ID that matches the exercise theme.",
  "youtube_id": "A real YouTube video ID (11 characters) of a tutorial for this exercise if you know one from training data, otherwise an empty string"
}
No explanation, no markdown, no code fences. Only raw JSON.'''},
                {'role': 'user', 'content': f'Generate exercise details for: {name}'}
            ],
            temperature=0.4,
            max_tokens=1000
        )
        text = response.choices[0].message.content.strip()
        text = text.replace('```json', '').replace('```', '').strip()
        details = json_mod.loads(text)
        save_ai_exercise_details(name, details)
        return jsonify({'success': True, 'details': details})
    except Exception as e:
        return jsonify({'error': str(e)})





# USER PROFILE


@app.route('/account/account-status')
@login_required
def account_status():
    """Grace-period / deactivated landing page. Blocks normal use via before_request."""
    user_dict = get_user_by_id(current_user.id)
    days_left = account_days_left(user_dict) if user_dict.get('account_status') == 'pending_delete' else None
    if user_dict.get('account_status') == 'active':
        return redirect(url_for('home'))
    return render_template('account_status.html',
        user=user_dict,
        status=user_dict.get('account_status', 'active'),
        days_left=days_left
    )


@app.route('/account/reactivate', methods=['POST'])
@login_required
def account_reactivate():
    """Restore the account immediately (keeps data intact)."""
    reactivate_account(current_user.id)
    flash('Welcome back! Your account is active again.')
    return redirect(url_for('home'))


@app.route('/account/restore/<token>')
def account_restore_token(token):
    """Restore via the email link; also ends up logging the user in."""
    uid = restore_account_by_token(token)
    if uid is None:
        flash('This restore link is invalid or has already been used.')
        return redirect(url_for('login'))
    user_dict = get_user_by_id(uid)
    login_user(User(user_dict))
    session.pop('guest', None)
    flash('Your account has been restored. Welcome back!')
    return redirect(url_for('home'))


@app.route('/account/deactivate', methods=['POST'])
@login_required
def account_deactivate():
    reason = (request.form.get('reason') or '').strip()
    set_account_status(current_user.id, 'deactivated')
    user_dict = get_user_by_id(current_user.id)
    token = set_restore_token(current_user.id)
    session.pop('guest', None)
    # Email a reactivation link (also lets password-less Google users recover)
    try:
        reactivate_url = url_for('account_restore_token', token=token, _external=True)
        send_deactivation_email(user_dict['email'], user_dict.get('first_name') or user_dict['name'], reactivate_url)
    except Exception as e:
        print(f"[Account Lifecycle] Deactivation email failed: {e}")
    logout_user()
    flash('Your account has been deactivated. You can reactivate any time by logging in or using the link we emailed you.')
    return redirect(url_for('login'))


@app.route('/account/delete/request-code', methods=['POST'])
@login_required
def account_delete_request_code():
    """Generate and email a 6-digit code to verify deletion intent via Gmail."""
    user_dict = get_user_by_id(current_user.id)
    code = f"{random.randint(0, 999999):06d}"
    expiry = datetime.now() + timedelta(minutes=DELETE_CODE_TTL_MINUTES)
    set_delete_email_code(current_user.id, code, expiry)
    try:
        send_delete_code_email(user_dict['email'].strip().lower(), user_dict.get('first_name') or user_dict['name'], code)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': f'Could not send email: {e}'})


@app.route('/account/delete/verify', methods=['POST'])
@login_required
def account_delete_verify():
    """Validate the emailed code. On success the frontend moves to "reasons"."""
    data = request.get_json(silent=True) or {}
    code = str(data.get('code', '')).strip().replace(' ', '')
    user_dict = get_user_by_id(current_user.id)
    stored = user_dict.get('delete_email_code') or ''
    expiry = user_dict.get('delete_email_code_expiry')
    if not stored or not expiry:
        return jsonify({'error': 'No verification code was sent. Please request a new one.'})
    try:
        expired = datetime.now() > datetime.fromisoformat(str(expiry).replace('Z', ''))
    except Exception:
        expired = True
    if expired:
        clear_delete_email_code(current_user.id)
        return jsonify({'error': 'This code has expired. Please request a new one.'})
    if code != stored:
        return jsonify({'error': 'Incorrect code. Please check your email and try again.'})
    return jsonify({'ok': True})


@app.route('/account/delete/confirm', methods=['POST'])
@login_required
def account_delete_confirm():
    """Final step: schedule permanent deletion after the 30-day grace period."""
    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip()
    if reason not in DELETE_REASONS and reason != '':
        reason = 'Something else'
    grant_delete_grace(current_user.id, reason if reason else None)
    user_dict = get_user_by_id(current_user.id)
    token = set_restore_token(current_user.id)
    try:
        restore_url = url_for('account_restore_token', token=token, _external=True)
        send_deletion_confirmation_email(
            user_dict['email'].strip().lower(),
            user_dict.get('first_name') or user_dict['name'],
            DELETE_GRACE_DAYS,
            restore_url
        )
    except Exception as e:
        print(f"[Account Lifecycle] Deletion confirmation email failed: {e}")
    return jsonify({'ok': True})

@app.route('/profile')
@login_required
def profile():
    user_dict = get_user_by_id(current_user.id)
    streak = get_streak(current_user.id)
    history_count = len(get_history(current_user.id, limit=1000))
    stats = get_summary(current_user.id)
    return render_template('profile.html',
        user=user_dict,
        streak=streak,
        history_count=history_count,
        stats=stats,
        reasons=DELETE_REASONS
    )


@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    first_name = request.form.get('first_name', '').strip()
    last_name  = request.form.get('last_name', '').strip()
    name       = f"{first_name} {last_name}".strip()
    email = request.form.get('email', '').strip().lower()
    username = request.form.get('username', '').strip().lower()

    if not first_name or not email:
        flash('Name and email are required.')
        return redirect(url_for('profile'))

    if email_exists(email, current_user.id):
        flash('That email is already used by another account.')
        return redirect(url_for('profile'))

    if username and username_exists(username, current_user.id):
        flash('This username is already taken.')
        return redirect(url_for('profile'))

    phone        = request.form.get('phone', '').strip()
    bio          = request.form.get('bio', '').strip()
    fitness_goal = request.form.get('fitness_goal', '').strip()
    kwargs = dict(first_name=first_name, last_name=last_name)
    if username:
        kwargs['username'] = username
    update_user_profile(current_user.id, name, email, phone, bio, fitness_goal, **kwargs)

    # Profile photo upload (optional)
    file = request.files.get('avatar')
    if file and file.filename:
        if not _allowed_avatar(file.filename):
            flash('Profile photo must be a PNG, JPG, GIF, or WEBP image.')
            return redirect(url_for('profile'))
        avatar_data = file.read()
        avatar_mime = mimetypes.guess_type(file.filename)[0] or 'image/png'
        # Capture any legacy file so it can be deleted after the switch to DB storage
        user_dict = get_user_by_id(current_user.id)
        legacy = (user_dict or {}).get('avatar') or ''
        legacy_path = None
        if legacy and legacy != 'db':
            legacy_path = _os.path.join(UPLOAD_DIR, _os.path.basename(legacy))
        update_user_avatar(current_user.id, avatar_data=avatar_data, avatar_mime=avatar_mime)
        if legacy_path and _os.path.exists(legacy_path):
            try:
                _os.remove(legacy_path)
            except OSError:
                pass

    flash('Profile updated successfully.')
    return redirect(url_for('profile'))


@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    current_pw  = request.form.get('current_password', '')
    new_pw      = request.form.get('new_password', '')
    confirm_pw  = request.form.get('confirm_password', '')

    user_dict = get_user_by_id(current_user.id)

    if not check_password_hash(user_dict['password_hash'], current_pw):
        flash('Current password is incorrect.')
        return redirect(url_for('profile'))

    if len(new_pw) < 6:
        flash('New password must be at least 6 characters.')
        return redirect(url_for('profile'))

    if new_pw != confirm_pw:
        flash('New passwords do not match.')
        return redirect(url_for('profile'))

    update_password(current_user.id, generate_password_hash(new_pw))
    flash('Password changed successfully.')
    return redirect(url_for('profile'))



@app.route('/reset_all_progress', methods=['POST'])
@login_required
def reset_all_progress():
    from data import load_progress, save_progress
    progress = load_progress(current_user.id)
    for day, exercises in progress.items():
        for exercise in exercises:
            save_progress(current_user.id, day, exercise, False)
    flash('All progress has been reset.')
    return redirect(url_for('profile'))


if __name__ == '__main__':
    app.run(debug=True)