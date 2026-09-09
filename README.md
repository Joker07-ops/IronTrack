# IronTrack

> Train hard. Track smart.

IronTrack is a free, self-hostable workout tracker and gym log with a built-in AI fitness
assistant. Plan your week, log each exercise, revisit your history, monitor your health and
get coached — all in one place, without subscriptions or ads.

## Features

- **Workout Tracker** — a 9-day training plan (Chest, Legs, Back, Shoulders, Arms, Core,
  Cardio, Full Body, Rest). Mark exercises complete, add/remove exercises, and use the
  built-in rest timer.
- **Training Templates** — prebuilt plans for every goal (build muscle, lose weight, etc.),
  applied to your schedule with one click.
- **Health Calculator** — BMI and health-category feedback with visual results.
- **Progress Charts** — interactive charts (React + Chart.js, no CDN) showing completion
  rate and a day-by-day breakdown.
- **Workout History** — a full timestamped log, filterable by exercise and date.
- **AI Assistant (IronBot)** — chat with a Groq-powered coach, generate personalized
  workouts, and get AI-generated exercise details (benefits + video quality notes).
- **Account system** — email + password and Google Sign-In (OAuth), email verification,
  password reset, and a 3-step account deletion flow with a 30-day grace period.
- **Profile page** — Instagram-style profile with avatar (upload via camera badge), stats,
  fitness goals, and security settings.
- **Feedback inbox** — users can leave feedback; admins (see `ADMIN_EMAILS`) can reply and
  manage it from `/admin/feedback`.
- **Fast by design** — a token-based design system (`css/tokens.css`), hand-written SVG icon
  sprite, local fonts and vendored JS — zero external CDN dependencies.
- **Responsive** — pixel-tested from 320px mobile screens up to desktop.

## Tech Stack

| Layer     | Technology |
|-----------|------------|
| Backend   | Flask, Flask-Login, Flask-Mail, Flask-Limiter |
| Database  | dual backend: SQLite (local `gymtrack.db`) or Postgres via `DATABASE_URL` (serverless) |
| Frontend  | Jinja2, vanilla JS, React (charts), CSS design tokens |
| AI        | Groq API, Google Gemini helper |
| Auth      | Email/password + Google OAuth 2.0 (Authlib) |
| Deploy    | gunicorn (see `Procfile`) or Vercel serverless (see `vercel.json`) |

## Getting Started

### Prerequisites

- Python 3.12+
- (Optional) a Groq API key for the AI assistant
- (Optional) Google OAuth credentials for Sign-In with Google

### 1. Clone & install

```bash
git clone https://github.com/<your-user>/gym_tracker.git
cd gym_tracker

python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in the values you need:

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

The app runs with an empty `.env` too — AI features, Google Sign-In and email are simply
disabled until you add the keys. `SECRET_KEY` is auto-generated into `.secret_key` on first
start if you don't set one.

### 3. Run

```bash
python app.py
```

Open http://127.0.0.1:5000 — the SQLite database and tables are created automatically on
startup.

## Environment Variables

| Variable                | Required | Description |
|-------------------------|----------|-------------|
| `SECRET_KEY`            | optional | Flask session signing key. Auto-generated to `.secret_key` if unset. |
| `GROQ_API_KEY`          | optional | Enables the IronBot AI assistant + AI-generated exercise details. |
| `GEMINI_API_KEY`        | optional | Used by `gemini_workout.py` for alternative AI workout generation. |
| `MAIL_USERNAME`         | optional | Gmail address used as SMTP sender (password reset, verification emails). |
| `MAIL_PASSWORD`         | optional | Gmail app password. `MAIL_USERNAME` + this enable Flask-Mail. |
| `GOOGLE_CLIENT_ID`      | optional | Google OAuth client ID for Sign-In with Google. |
| `GOOGLE_CLIENT_SECRET`  | optional | Google OAuth client secret. |
| `ADMIN_EMAILS`          | optional | Comma-separated list of emails with access to the admin feedback inbox. |
| `SITE_URL`              | optional | Canonical site URL (used for SEO URLs in meta tags). |
| `DATABASE_URL`          | prod | Postgres connection string. When set, Postgres is used (e.g. on Vercel); otherwise SQLite (`gymtrack.db`). |
| `SESSION_COOKIE_SECURE` | optional | Send session cookies over HTTPS only. Defaults to `true` on Vercel, `false` locally. |
| `PREFERRED_URL_SCHEME`  | optional | Forces redirect scheme to `https` behind a proxy. Defaults to `https` on Vercel. |

### Google OAuth notes

Register the following URLs as **Authorized redirect URIs** in your Google Cloud console:

- `http://127.0.0.1:5000/login/google/authorized` (local)
- `https://your-domain.com/login/google/authorized` (production)

## Project Structure

```
├── app.py                 # App factory, routes and startup DB init
├── api/index.py           # Vercel serverless entrypoint (WSGI)
├── database.py            # Dual-backend schema (SQLite + Postgres) + seed logic
├── data.py                # Data access layer (users, progress, chat, feedback, …)
├── workout.py             # Workout plan + progress business logic
├── exercises.py           # Built-in exercise catalogue
├── workout_templates.py   # Prebuilt training plan templates
├── gemini_workout.py      # Gemini-based workout generation helper
├── requirements.txt
├── vercel.json                 # Vercel serverless config
├── Procfile / runtime.txt      # gunicorn config (Render / Heroku)
├── css/                        # Design tokens, app styles, auth styles (served via /css/)
├── templates/                  # Jinja2 templates (incl. base.html, auth_base.html)
└── static/
    ├── icons/sprite.svg        # Hand-written Lucide-style SVG sprite
    ├── fonts/                  # Self-hosted Roboto / Roboto Condensed
    ├── libs/                   # Vendored React + Chart.js
    ├── react-analytics.js      # Theme-aware chart component (plain JS)
    ├── sw.js                   # Service worker
    └── uploads/                # Legacy local-only profile photos (not committed)
```

## Deployment

### Option A — Vercel (serverless)

The app ships with a Vercel serverless entrypoint (`api/index.py` + `vercel.json`). It uses
a Postgres database — set these environment variables in your Vercel project:

1. Create a free Postgres database (e.g. [Neon](https://neon.tech) or
   [Supabase](https://supabase.com)) and copy its connection string.
2. In Vercel → project → **Settings → Environment Variables** add:
   - `DATABASE_URL` — your Postgres connection string (hostname must be `postgres.…` /
     `-pooler.…`, not inlined credentials with dashes in the password).
   - `SECRET_KEY` — a long random string (sessions reset per instance otherwise).
   - `SITE_URL` — e.g. `https://your-app.vercel.app`.
   - Optional: `GROQ_API_KEY`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `GOOGLE_CLIENT_ID`,
     `GOOGLE_CLIENT_SECRET`, `ADMIN_EMAILS`.
3. Import the repo on Vercel (Framework Preset: **Other**). The build/start commands are
   handled automatically by `vercel.json`.

> **Note:** serverless filesystems are read-only — profile photos are stored in the
> database (served via `/avatar/<id>`) instead of on disk.

### Option B — Heroku / Render (always-on)

```bash
# Procfile
web: gunicorn app:app
```

For production, set `SITE_URL` to your canonical URL so the `PREFERRED_URL_SCHEME`
handles redirects correctly behind a reverse proxy.

## License

[MIT](LICENSE)