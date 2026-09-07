# Hostel AI — Grievance Severity Prediction System

An AI-powered hostel complaint management system built with Django. It classifies
every complaint's severity (Low / Medium / High / Critical), gives the assigned
warden a priority-based deadline to resolve it, and gives every role — Student,
Parent, Warden, Admin — a dashboard with live analytics.

## Two separate login portals

| Portal | URL | Who can sign in |
|--------|-----|------------------|
| **Main portal** | `/login/` | Students & Parents only |
| **Staff portal** | `/staff-login/` | Wardens & Admins only |

Each portal rejects the wrong role with a helpful message pointing to the
correct page (e.g. a Warden trying `/login/` is told to use the Staff Login
instead). This keeps the public-facing sign-in clearly separated from the
staff-only sign-in used by hostel administration.

## Four separate "create account" pages

Each role has its own **dedicated** sign-up page — not a shared form with a
role dropdown. Every page only asks for that role's own username & password
(the Parent page additionally creates the child's account in the same step).

| Role | Page | What it asks for |
|------|------|-------------------|
| **Student** | `/signup/student/` | Own username & password + hostel room |
| **Parent**  | `/signup/parent/` | Own username & password, **and** their child's name/username/password/room (creates both accounts together) |
| **Warden**  | `/signup/warden/` | Own username & password + staff signup code |
| **Admin**   | `/signup/admin/` | Own username & password + staff signup code |

`/signup/` is a hub page that links to all four. Each dedicated page also
links back to the hub ("Choose a different account type") and to the
matching sign-in page.

## Who can create an account, and how

| Role    | How the account is created |
|---------|------------------------------|
| **Student** | Self-registers at `/signup/student/`. |
| **Parent**  | Self-registers at `/signup/parent/` — creates their child's student login at the same time, so the parent-child link is always correct (no separate step, no guessing usernames). |
| **Warden**  | Self-registers at `/signup/warden/` with their **own** username & password. Requires the shared **staff signup code** (see below). |
| **Admin**   | Self-registers at `/signup/admin/` the same way — or created with `python manage.py createsuperuser` (automatically gets Role = Admin). |

This app ships with **no seed/demo data** — every account you see is one that
was actually created through one of the flows above.

### The staff signup code

Since `/signup/admin/` can create Admin accounts (full CRUD access), it's
gated by a shared code so random visitors can't grant themselves elevated
access. The default is:

```
HOSTELAI-STAFF-2026
```

Set your own in production via an environment variable before deploying:

```bash
export STAFF_SIGNUP_CODE="something-only-your-staff-know"
```

(See `hostelai/settings.py` → `STAFF_SIGNUP_CODE`.) Share this code only with
people who should be able to create Warden/Admin accounts.

## Features

- **AI severity engine** (`grievance/ai_engine.py`) — if you set a `GEMINI_API_KEY`
  environment variable, complaints are analyzed by Gemini. Without a key, the app
  automatically falls back to a transparent rule-based keyword/weight scorer, so
  it runs perfectly with **zero external API keys**.
- **Priority-based warden allocation time** — every complaint gets an automatic
  resolution deadline based on its predicted severity:
  - Critical → 2 hours
  - High → 8 hours
  - Medium → 24 hours
  - Low → 72 hours
  (Configurable in `hostelai/settings.py` → `SEVERITY_ALLOCATION_HOURS`.)
- **Warden priority queue** — sorted by severity, then nearest deadline, with
  overdue items flagged in red.
- **Image upload** on complaints (Pillow), category tagging (Food / Room /
  Maintenance / Ragging-Safety / Other), full audit trail of status changes.
- **Role dashboards with Chart.js analytics**: category/severity/status
  breakdowns, warden workload, average resolution time, overdue counts.
- **Full CRUD** for Admins via the built-in Django admin at `/admin/` —
  rebranded as "Hostel AI · Control Panel" with the app's own colors/fonts
  instead of the default "Django administration" look (see
  `grievance/admin.py` and `static/css/admin_theme.css`).

## Quick start

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py runserver
```

Visit **http://127.0.0.1:8000/**.

### 1. Create your first Admin account

Two ways:

- **Via the app**: go to `/signup/admin/`, set your own username/password,
  and enter the staff signup code (`HOSTELAI-STAFF-2026` by default — see
  "The staff signup code" above).
- **Via the command line**:
  ```bash
  python manage.py createsuperuser
  ```
  Follow the prompts (username/email/password). This account automatically
  gets **Role = Admin**.

Either way, log in at `/staff-login/` to reach the full Control Room
dashboard, or at `/admin/` for raw CRUD access.

### 2. Wardens sign themselves up too

Go to `/signup/warden/` → set your own username and password → enter the
staff signup code. No admin needs to manually create the account, and the
form never asks for (or contains) a student or parent username.

### 3. Students and Parents sign themselves up

From the login page, click **"Create an account"** to reach the hub at
`/signup/`, then pick one:
- **Student** (`/signup/student/`) → enters their own name/username/password + hostel room.
- **Parent** (`/signup/parent/`) → enters their own name/username/password, *and* in the same
  form creates their child's student account (child's name, username,
  password, hostel room). The parent-child link is created automatically —
  no separate step, and no risk of linking to the wrong or a non-existent
  student account.

## Enabling real Gemini AI (optional)

By default the severity engine uses a built-in rule-based scorer — no API key
required. To use real Gemini analysis instead:

```bash
pip install google-generativeai
export GEMINI_API_KEY="your-key-here"
# optional: export GEMINI_MODEL_NAME="gemini-1.5-flash"
```

Uncomment `google-generativeai` in `requirements.txt`. The app automatically
detects the key and switches engines — no code changes needed. If the Gemini
call ever fails (bad key, network, rate limit), it silently falls back to the
rule-based engine so complaints are never left unclassified.

## Project structure

```
hostelai/
├── manage.py
├── requirements.txt
├── hostelai/            # project settings & urls
└── grievance/           # the app: models, views, forms, admin, ai_engine
    ├── models.py         # User, StudentProfile, Complaint, ComplaintUpdate
    ├── ai_engine.py       # Gemini + rule-based severity engine
    ├── views.py           # role dashboards + complaint CRUD
    ├── forms.py           # signup (student / parent+child), complaint forms
    └── admin.py           # full CRUD via Django admin (create Warden/Admin here)
templates/                # all HTML templates (Bootstrap 5 + Chart.js via CDN)
static/css/style.css       # custom design system
```

## Notes

- This ships with `DEBUG = True` and a permissive `ALLOWED_HOSTS` for easy local
  running. **Before deploying to production**, set `DEBUG = False`, set a real
  `SECRET_KEY` from an environment variable, restrict `ALLOWED_HOSTS`, and switch
  to Postgres/MySQL.
- SQLite is used out of the box — no database setup needed to try it locally.
- There is no seed/demo data command in this build — create your own Admin
  with `createsuperuser`, then add Wardens and let Students/Parents sign up.
