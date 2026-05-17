# OurTime

A privacy-first collaborative scheduling tool for small groups. No account required to participate — anyone with a link can mark their availability with **Yes / Maybe / No** per time slot. Results show as an aggregate overlap grid; no individual responses are ever exposed to the event creator or other participants.

## Features

- **No login required to respond** — share a link, anyone can participate
- **Yes / Maybe / No per hour** — richer than binary availability, overlap ranked by score
- **Anonymous by design** — event admins see respondent counts, never names or individual answers
- **Optional persistent accounts** — reserve a username across events; OAuth-free, email + passphrase only
- **Encrypted at rest** — AES-256-GCM on all PII fields, Argon2id for passwords, HMAC-SHA256 for lookups; keys never touch the DB
- **No third-party scripts** — Alpine.js self-hosted, no CDN calls at runtime
- **API-first** — every action goes through a documented REST API; frontend is a thin Alpine.js layer

---

## Table of Contents

- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Creating an Event](#creating-an-event)
  - [Submitting Availability](#submitting-availability)
  - [Viewing Results](#viewing-results)
  - [Persistent Accounts](#persistent-accounts)
- [Administration](#administration)
  - [Event Admin](#event-admin)
  - [Site Admin](#site-admin)
  - [Deployment](#deployment)
  - [Configuration Reference](#configuration-reference)
- [Maintenance](#maintenance)
  - [Updating](#updating)
  - [Backups](#backups)
  - [Running Tests](#running-tests)
  - [Database](#database)
- [Contributing](#contributing)
- [License](#license)

---

## Quick Start

### Local development

```bash
git clone https://github.com/jedmitten/ourtime.us.git
cd ourtime.us
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit .env — see Configuration Reference
uvicorn backend.main:app --reload --port 8000
```

Open `http://localhost:8000`.

### Docker (recommended for production)

```bash
git clone https://github.com/jedmitten/ourtime.us.git
cd ourtime.us
cp .env.example .env          # edit .env before first run
docker compose up -d
```

---

## Usage

### Creating an Event

1. Visit the home page and click **Create Event**.
2. Enter a title and optional description.
3. Select your **timezone** — auto-detected from your browser, editable.
4. Pick the **availability window**: start and end date using the calendar picker. Respondents can mark any day within this range.
5. Set **daily time bounds**: the earliest and latest hour respondents may select each day (e.g. 8 am – 11 pm).
6. Submit. You receive two things — **save both**:
   - **Share URL** — send this to everyone you want responses from.
   - **Admin token** — gives you access to the admin panel. It is shown exactly once and not stored in recoverable form; if lost, you cannot manage the event.

### Submitting Availability

1. Open the share URL.
2. Enter a display name. If the name is already registered to a persistent account, you will be asked to sign in or choose a different name.
3. Optionally check **"Save this name for future events"** and provide an email + passphrase to create a persistent account inline.
4. The calendar shows every month in the event window. Click days to select them (click again to deselect; click and drag to select a range).
5. For each selected day, an hour strip appears. Click any hour to cycle through: **unset → Yes → Maybe → No → unset**. Use the **All Yes / All Maybe / All No / Clear** buttons to mark an entire day at once.
6. Submit. Ephemeral users receive an **edit token link** — save it to update your response later. Account holders can return via **My Account**.

### Viewing Results

The **See Results** tab is visible to anyone with the share URL.

- A **heat-map calendar** colors each day by overall score (`yes × 2 + maybe − no × 2`).
- Click any day to see the **hour breakdown** — yes / maybe / no counts per hour.
- A **ranked list** of the top time slots appears below the calendar.
- The results page refreshes automatically every 30 seconds.

No names are shown at any point. The page shows only aggregate counts.

### Persistent Accounts

Creating an account is optional and never required to respond to an event.

Benefits:
- Your username is reserved globally — no one else can use it in any event, even ephemerally.
- You can find all events you have participated in at **My Account → My Events**.
- You can edit past responses without saving an edit token.

**Register** at `/me`, or inline when submitting to an event.  
**Recover a lost passphrase** via the "Forgot passphrase?" link — a magic link is sent to your registered email, valid for 15 minutes.

---

## Administration

### Event Admin

Each event has one admin, identified by the admin token issued at creation.

Access the admin panel at `/admin/{event_id}` — paste your admin token when prompted, or append it as `?key={token}` to auto-fill.

The admin panel shows:
- Total number of respondents (no names, no individual data)
- Event window and expiry date
- A link to the public results view
- **Delete Event** — permanently removes the event and all associated responses after a confirmation step

There is no way to recover a lost admin token. If lost, the event continues to work for respondents but cannot be managed or deleted by the creator. Events auto-delete after the configured expiry period (default: 90 days after the last day in the window).

### Site Admin

The site admin has one capability: **transferring ownership of a username** (e.g. when a user loses access to their account and email). This is an operator-level action and bypasses normal authentication.

```bash
curl -X POST https://yoursite.example.com/api/site-admin/transfer-username \
  -H "X-Site-Admin-Secret: YOUR_SITE_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "new_passphrase": "temporary-password-123"}'
```

This invalidates all existing sessions for that account and sets a new passphrase. The user then logs in with the new passphrase and should change it immediately.

The site admin secret is set via the `SITE_ADMIN_SECRET` environment variable and never stored in the database.

### Deployment

#### Synology Container Manager

1. Clone the repo to your Synology (via SSH or File Station).
2. Copy and fill in the environment file:
   ```bash
   cp .env.example .env
   nano .env
   ```
3. Start the container:
   ```bash
   docker compose up -d
   ```
4. In **Synology Control Panel → Application Portal → Reverse Proxy**, create a rule:
   - Source: `https://yoursite.example.com` (HTTPS, port 443)
   - Destination: `http://localhost:8000`
   - Enable **Let's Encrypt** for automatic TLS.

#### Other platforms

The app ships as a standard Docker image and runs anywhere Docker runs. Platforms known to work with no code changes:

- **Fly.io** — `fly launch` from the repo root; add a persistent volume at `/app/data`.
- **Railway** — connect the repo; set env vars in the dashboard; add a volume for `/app/data`.
- Any Linux VPS running Docker.

SQLite is suitable for the intended use case (small groups, low concurrency). For higher traffic, the data layer can be migrated to PostgreSQL by swapping `aiosqlite` for `asyncpg` and adjusting the schema — the application logic does not change.

### Configuration Reference

All configuration is via environment variables (or a `.env` file in the project root).

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | 64-character hex string. Used as HKDF master key for AES encryption and HMAC lookups. Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `SITE_ADMIN_SECRET` | Yes | — | Site admin password. Used only for username transfers. |
| `BASE_URL` | Yes | `http://localhost:8000` | Public-facing URL with no trailing slash. Used in recovery email links. |
| `DB_PATH` | No | `data/ourtime.db` | Path to SQLite database file. The directory is created automatically. |
| `EVENT_EXPIRY_DAYS` | No | `90` | Days after creation before an event auto-deletes. |
| `SMTP_HOST` | No | _(empty)_ | SMTP server hostname. Leave empty to disable email; recovery tokens print to stdout instead. |
| `SMTP_PORT` | No | `587` | SMTP port. |
| `SMTP_USER` | No | _(empty)_ | SMTP username. |
| `SMTP_PASSWORD` | No | _(empty)_ | SMTP password. |
| `SMTP_FROM` | No | `noreply@localhost` | From address for recovery emails. |
| `SMTP_TLS` | No | `true` | Use STARTTLS for SMTP. |

> **Rotating `SECRET_KEY`** invalidates all encrypted fields in the database (event titles, descriptions, user emails, usernames). Do not rotate without a migration plan. Admin tokens, edit tokens, and session tokens are stored as SHA-256 hashes and are unaffected by key rotation.

---

## Maintenance

### Updating

```bash
git pull
docker compose up -d --build   # rebuilds the image with new code
```

The database schema uses `CREATE TABLE IF NOT EXISTS` — schema additions are safe to run on startup without data loss. Breaking schema changes will be noted in the changelog.

### Backups

The entire application state lives in a single SQLite file. Back it up by copying `data/ourtime.db` while the app is idle, or use SQLite's online backup:

```bash
sqlite3 data/ourtime.db ".backup data/ourtime.backup.db"
```

For scheduled backups on Synology, use Task Scheduler to run the above command and copy the output to a backup share. The database is typically small (a few MB for typical usage).

To restore, stop the container, replace `data/ourtime.db` with your backup, and restart.

### Running Tests

```bash
python -m pytest tests/ -v
```

128 tests cover all API endpoints, privacy invariants, and end-to-end flows. Tests run against a temporary in-memory database and do not touch the production database.

Run tests before deploying any local changes:

```bash
python -m pytest tests/ -q && docker compose up -d --build
```

### Database

The app uses SQLite in WAL mode. Direct inspection:

```bash
sqlite3 data/ourtime.db
```

Useful queries:

```sql
-- Active events
SELECT id, window_start, window_end, expires_at FROM events ORDER BY created_at DESC;

-- Respondent counts per event
SELECT event_id, COUNT(*) as respondents FROM submissions GROUP BY event_id;

-- Delete expired events manually (the app does this on access, not on a schedule)
DELETE FROM events WHERE expires_at < datetime('now');
```

Note: event titles, descriptions, and usernames are AES-256-GCM encrypted in the database. They are not readable via direct SQL queries without the `SECRET_KEY`.

---

## Contributing

Contributions are welcome. Please open an issue before starting significant work so we can discuss the approach.

### Development setup

```bash
git clone https://github.com/jedmitten/ourtime.us.git
cd ourtime.us
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in SECRET_KEY and SITE_ADMIN_SECRET
uvicorn backend.main:app --reload --port 8000
```

### Guidelines

- **Run the test suite before opening a PR.** All 128 tests must pass: `python -m pytest tests/ -q`
- **Add tests for new API behaviour.** Aim to cover happy paths, error paths, and any privacy/security invariants.
- **Privacy properties are non-negotiable.** Do not add features that expose individual respondent data to event admins or other participants. Any change that touches auth, encryption, or anonymity requires extra scrutiny.
- **Keep the frontend dependency-free.** No new external scripts or CDN calls. If a JS library is needed, vendor it under `frontend/static/`.
- **Follow existing code style.** The backend uses standard FastAPI/Pydantic patterns; the frontend uses Alpine.js components with no build step.
- **No AI-generated commit messages** that reference the tool used to write them.

### Branch and PR conventions

- Branch from `main`.
- Use `type/short-description` naming: `feat/results-export`, `fix/timezone-edge-case`, `docs/deployment-guide`.
- PR titles should be imperative and specific: `Add CSV export for results` not `Updates`.
- One logical change per PR.

### Reporting security issues

Please do not open a public GitHub issue for security vulnerabilities. Email the maintainer directly (see GitHub profile). Include a description of the issue, steps to reproduce, and your assessment of impact. You will receive a response within 48 hours.

---

## License

[MIT](LICENSE) — see the LICENSE file for full text.
