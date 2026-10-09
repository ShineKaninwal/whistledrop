# WhistleDrop — Anonymous Reporting Platform

Report wrongdoing without an account and without giving your name. Built with FastAPI for the GDG on Campus SRM Technical Recruitment 2026 (Backend task).

---

## 1. Problem

People who see harassment, corruption or a security hole often stay silent because reporting means identifying themselves. Existing channels (email, forms tied to a login) put a name next to the report.

## 2. Solution

WhistleDrop lets anyone submit a report with **no name, email, phone number, account or password**. The server answers with a random **case code** (for example `WD-7K4P9X2M`). The reporter keeps that code and uses *only* the code to see whether the report is `SUBMITTED`, `UNDER_REVIEW`, `RESOLVED` or `DISMISSED`, and to read the moderator's latest message. Moderators sign in to a dashboard to review reports and update their status.

## 3. Features

- Anonymous report submission (category, description, optional evidence URL)
- Cryptographically random, unique case codes
- Public status lookup by case code, returning only what the reporter needs
- Moderator login (bcrypt + JWT), protected endpoints
- Enforced report lifecycle: `SUBMITTED → UNDER_REVIEW → RESOLVED | DISMISSED`
- Moderator filtering (category, status, text search, date range) and pagination
- Statistics endpoint
- Moderator dashboard (plain HTML/CSS/JS) with live totals, filters, detail drawer, toasts, light/dark theme
- Swagger / OpenAPI at `/docs`
- Automated pytest suite on an isolated test database
- Docker and `docker compose up` support

## 4. Architecture

```
Browser (dashboard)  ──┐
Swagger UI / curl    ──┼──►  FastAPI app
Reporter (any client)──┘       │
                               ├── routers/    HTTP layer: parse request, call a service, wrap response
                               ├── services/   business logic: case codes, workflow rules, queries
                               ├── auth/       password hashing, JWT, "who is the moderator?" dependency
                               ├── schemas/    Pydantic models: validation + exactly what is returned
                               ├── models/     SQLAlchemy tables
                               └── SQLite (SQLAlchemy ORM)
```

```
whistledrop/
├── app/
│   ├── main.py            app setup, error handlers, security headers, serves the dashboard
│   ├── config.py          environment-based settings (fails fast on weak production config)
│   ├── database.py        engine, session, get_db dependency
│   ├── create_moderator.py  CLI to create/reset a moderator
│   ├── seed_demo.py       optional fake demo reports
│   ├── models/            Report, Moderator, enums
│   ├── schemas/           request/response models
│   ├── routers/           reports.py (public), auth.py, moderator.py
│   ├── services/          report_service.py, workflow.py
│   ├── auth/              security.py (bcrypt, JWT), dependencies.py, service.py
│   └── utils/             case_code.py, errors.py, responses.py, time.py
├── dashboard/             index.html, style.css, app.js
├── tests/                 pytest suite
├── .env.example  .gitignore  requirements.txt  requirements-dev.txt
├── Dockerfile  docker-compose.yml  pytest.ini  README.md
```

The rule of thumb: **routers know HTTP, services know the rules, schemas decide what leaves the server.**

## 5. Tech stack

Python 3.10+ · FastAPI · SQLAlchemy 2.0 · SQLite · Pydantic v2 · PyJWT · bcrypt · pytest · Docker · vanilla HTML/CSS/JS.

## 6. Database design

**reports**

| Column | Type | Notes |
|---|---|---|
| `id` | integer, PK | internal only, **never returned by any endpoint** |
| `case_code` | string(16), unique index | public identifier, random |
| `category` | string, index | SECURITY, HARASSMENT, CORRUPTION, TECHNICAL, OTHER |
| `description` | text | 10–5000 characters |
| `evidence_url` | string, nullable | http/https only |
| `status` | string, index | the four lifecycle states |
| `status_message` | string(500), nullable | moderator update shown to the reporter |
| `created_at` / `updated_at` | UTC datetime, `created_at` indexed | |

**moderators**: `id`, `username` (unique), `password_hash` (bcrypt), `created_at`.

There is deliberately no column for a name, email, phone number, IP address or user agent. The unique index on `case_code` makes lookups fast and guarantees uniqueness at the database level.

## 7. API endpoints

All JSON. Interactive docs: `/docs`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/reports` | none | Submit an anonymous report (201) |
| GET | `/api/reports/{case_code}` | none | Public status of a report |
| POST | `/api/auth/login` | none | Moderator login, returns JWT |
| GET | `/api/moderator/reports` | JWT | List reports (filters + pagination) |
| GET | `/api/moderator/reports/{case_code}` | JWT | Full report |
| PATCH | `/api/moderator/reports/{case_code}/status` | JWT | Change status and/or message |
| GET | `/api/moderator/stats` | JWT | Totals per status and category |
| GET | `/api/health` | none | Health check |

**Moderator list filters:** `category`, `status`, `q` (searches case code and description), `created_from`, `created_to` (UTC dates, inclusive), `page` (≥1), `page_size` (1–100, default 20).

**Response format**

```json
{ "success": true,  "data": { } }
{ "success": false, "error": { "code": "report_not_found", "message": "...", "details": null } }
```

| Status | When |
|---|---|
| 200 / 201 | success / report created |
| 400 | malformed JSON |
| 401 | missing, invalid or expired token; wrong login |
| 404 | unknown case code |
| 409 | invalid status transition |
| 422 | validation failure (field, case-code format, filters) |
| 500 | unexpected error (generic message, details stay in server logs) |

## 8. Authentication

- Moderators only. Reporters never authenticate.
- `POST /api/auth/login` checks the bcrypt hash and returns a signed JWT (HS256) containing the username, issue time and expiry (default 60 minutes).
- Send it as `Authorization: Bearer <token>`. In Swagger click **Authorize** and paste the token.
- Unknown username and wrong password return the same error and do the same amount of hashing work.
- There is no public sign-up. The first moderator is created on startup from `MODERATOR_USERNAME` / `MODERATOR_PASSWORD`, or with `python -m app.create_moderator --username alice` (also resets a password).

## 9. How anonymity is maintained

**What the application stores:** category, description, optional evidence URL, status, moderator message, timestamps, and a random case code.

**What it never collects or stores:** name, email, phone number, account, password, IP address, user agent, cookies or tracking identifiers. The submit endpoint rejects unknown fields (for example `"email"`), so identity cannot be added by accident.

**What the application does about leaks:**
- The database ID is never exposed; only the random case code identifies a report publicly.
- The public lookup returns five fields: `case_code`, `status`, `update`, `created_at`, `updated_at`. It does not return the description, category or evidence URL.
- Validation errors never echo what you submitted.
- Application logs never contain report content or case codes.
- `Cache-Control: no-store` on API responses; `Referrer-Policy: no-referrer`.

### Honest limits (read this)

WhistleDrop **does not provide perfect anonymity**. It collects no identity, but:

- **Network layer:** your IP address is visible to the hosting provider, any reverse proxy and your network. Web servers commonly log IPs by default. The Docker image runs uvicorn with `--no-access-log` for this reason; if you deploy behind a proxy or platform, check *its* logs. Reporters who need strong anonymity should use Tor Browser or a network they trust.
- **The text itself:** a description containing details only you would know can identify you. Moderators cannot protect you from that.
- **The case code is a secret:** anyone who has it can read the status message. Treat it like a password. Anyone who sees the URL (browser history, shared screen) sees the code.
- **Evidence links:** a moderator opening a link visits a third-party site. The dashboard opens links with `noopener noreferrer`, but the destination still sees the moderator's IP.
- **Timing:** someone who can watch both your network and the server could correlate when you submitted.
- **Data at rest:** SQLite is not encrypted. Protect the host and the volume.

## 10. Case-code generation

Format `WD-` + 8 characters from a 30-character alphabet (digits 2–9 and letters without I, L, O, U, so nothing is misread). Generated with Python's `secrets.choice` (the operating system's secure random source), never `random` and never derived from the database ID. That gives about 6.6 × 10¹¹ possibilities (~39 bits). Uniqueness is enforced by the database unique index; on a collision the service generates a new code and retries (up to 5 times). Input is trimmed and uppercased before the format is checked, so `wd-7k4p9x2m` works.

## 11. Report lifecycle

```
SUBMITTED ──► UNDER_REVIEW ──► RESOLVED
                           └─► DISMISSED
```

| From | Allowed next |
|---|---|
| SUBMITTED | UNDER_REVIEW |
| UNDER_REVIEW | RESOLVED, DISMISSED |
| RESOLVED, DISMISSED | none (final) |

Documented rules:
- `SUBMITTED → RESOLVED` (skipping review) is **rejected with 409**. Every report is reviewed first.
- Final statuses cannot change.
- Sending the *current* status together with a message only edits the message (the message is then required).
- If no message is given on a status change, the reporter sees a standard message for that status.

The transition table lives in one place: `app/services/workflow.py`.

## 12. Validation

| Input | Rule |
|---|---|
| category | one of the five values (case-insensitive) |
| description | required, 10–5000 characters after trimming |
| evidence_url | optional, must be a valid `http`/`https` URL (so `javascript:` is rejected) |
| extra fields | rejected |
| case code | must match `WD-` + 8 allowed characters |
| status | one of the four values |
| status message | optional, max 500 characters |
| JSON body | malformed JSON returns 400 |
| filters | enum values, valid dates, `created_from ≤ created_to`, `page ≥ 1`, `1 ≤ page_size ≤ 100` |

## 13. Security considerations

- bcrypt password hashing; plaintext passwords are never stored or logged
- JWT signed with `SECRET_KEY` from the environment, with required expiry
- All moderator routes protected by one router-level dependency
- Secrets only from environment variables; `.env` is git-ignored; `.env.example` is provided
- `APP_ENV=production` refuses to start without a 32+ character `SECRET_KEY` or with a weak/default moderator password
- Case codes from a CSPRNG
- CORS limited to configured origins, only the methods and headers the API needs, no cookies
- Dashboard renders all report text with `textContent` (no HTML injection) and is served with a strict Content-Security-Policy
- Stack traces are never sent to clients; unexpected errors return a generic 500
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`
- ORM queries only (no string-built SQL), so no SQL injection

## 14. Swagger documentation

Start the app and open **http://localhost:8000/docs** (ReDoc at `/redoc`, raw spec at `/openapi.json`). Every endpoint has a description, request/response models and documented error codes. Use **Authorize** to paste a moderator token.

## 15. Testing

`pytest` with FastAPI's `TestClient`. Each test gets a fresh in-memory SQLite database and a test moderator, so tests never touch your real data. They cover: anonymous creation, case-code format/uniqueness/collision retry, public lookup, invalid and malformed case codes, invalid report data and malformed JSON, login success/failure, rejected unauthenticated access to every moderator route, listing, detail, status update, full lifecycle, invalid transitions, filters, pagination, stats, and privacy (the public responses contain only the allowed fields and never echo input).

## 16. Local setup

Requires Python 3.10+.

```bash
git clone <your-repo-url> whistledrop
cd whistledrop
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
```

## 17. Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENV` | `development` | `production` enforces strong secrets |
| `SECRET_KEY` | random per start (dev only) | JWT signing key. **Required in production** (32+ chars) |
| `DATABASE_URL` | `sqlite:///./whistledrop.db` | SQLAlchemy URL |
| `ACCESS_TOKEN_MINUTES` | `60` | token lifetime |
| `CORS_ORIGINS` | none | comma-separated allowed origins |
| `MODERATOR_USERNAME` / `MODERATOR_PASSWORD` | none | account created on startup if missing |
| `BCRYPT_ROUNDS` | `12` | bcrypt cost |

Generate a secret: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

## 18. Running the project

```bash
uvicorn app.main:app --reload --no-access-log
```

| What | URL |
|---|---|
| Moderator dashboard | http://localhost:8000/dashboard/ |
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

With the default `.env.example`, sign in as `moderator` / `change-me-please` (local development only). Optional fake data for the dashboard: `python -m app.seed_demo`.

Docker: `docker compose up --build` (same URLs; demo login `moderator` / `moderator-demo-pass` unless you set your own in `.env`).

## 19. Running tests

```bash
pytest
```

## 20. Deployment

The same container runs anywhere Docker runs. It honours `$PORT`.

**Any VPS with Docker**
1. Create `.env` next to `docker-compose.yml` with `APP_ENV=production`, a strong `SECRET_KEY`, `MODERATOR_USERNAME`, a strong `MODERATOR_PASSWORD` and `CORS_ORIGINS` (your public URL).
2. `docker compose up -d --build`
3. Put a TLS reverse proxy (Caddy or nginx) in front. **Always use HTTPS** so case codes and tokens are encrypted in transit. Turn off IP logging in the proxy.

**Render (Docker web service)**
1. Push the repository to GitHub, create a *Web Service*, choose *Docker* as the runtime.
2. Add the environment variables above (`APP_ENV=production`, `SECRET_KEY`, `MODERATOR_USERNAME`, `MODERATOR_PASSWORD`).
3. Attach a persistent disk mounted at `/data` so the SQLite file survives deploys. Without a disk, data is lost on every redeploy (fine for a demo, not for real use).
4. Open `https://<your-service>.onrender.com/docs`.

Platform menus change, so check the provider's current docs for exact button names.

## 21. Example API requests and responses

**Submit a report**

```bash
curl -X POST http://localhost:8000/api/reports \
  -H "Content-Type: application/json" \
  -d '{"category":"SECURITY","description":"The admin panel is reachable without logging in.","evidence_url":"https://example.com/proof"}'
```
```json
{
  "success": true,
  "data": {
    "case_code": "WD-7K4P9X2M",
    "status": "SUBMITTED",
    "message": "Save this case code. It is the only way to check your report's status.",
    "created_at": "2026-10-04T10:15:30.123456Z"
  }
}
```

**Check status**

```bash
curl http://localhost:8000/api/reports/WD-7K4P9X2M
```
```json
{
  "success": true,
  "data": {
    "case_code": "WD-7K4P9X2M",
    "status": "SUBMITTED",
    "update": "Your report has been received and is waiting for review.",
    "created_at": "2026-10-04T10:15:30.123456Z",
    "updated_at": "2026-10-04T10:15:30.123456Z"
  }
}
```

**Moderator login and update**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"moderator","password":"change-me-please"}' | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

curl -X PATCH http://localhost:8000/api/moderator/reports/WD-7K4P9X2M/status \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status":"UNDER_REVIEW","message":"We have started looking into this."}'
```

**Invalid transition (409)**

```json
{
  "success": false,
  "error": {
    "code": "invalid_status_transition",
    "message": "Cannot change status from SUBMITTED to RESOLVED. Allowed: UNDER_REVIEW.",
    "details": null
  }
}
```

**Validation error (422)**

```json
{
  "success": false,
  "error": {
    "code": "validation_error",
    "message": "The request is invalid.",
    "details": [{ "field": "category", "message": "Input should be 'SECURITY', 'HARASSMENT', 'CORRUPTION', 'TECHNICAL' or 'OTHER'" }]
  }
}
```

## 22. Important design decisions

- **SQLite + SQLAlchemy:** zero setup for students and reviewers. Changing `DATABASE_URL` and installing a driver moves it to PostgreSQL.
- **Random case code, separate from the database ID:** sequential IDs are guessable, and exposing them reveals how many reports exist.
- **A single transition table:** one place to read, test and explain the rules.
- **409 for invalid transitions:** the request is well-formed but conflicts with the report's current state.
- **Skipping review is rejected** rather than allowed, so no report is closed unseen.
- **Consistent JSON envelope** for success and errors, so clients have one shape to handle.
- **Schemas pick the fields:** public responses are built from explicit models, so a new database column can never leak by accident.
- **Dashboard served by the API:** same origin means no CORS setup and one thing to deploy. It could be hosted separately by setting `API_BASE` in `dashboard/app.js` and `CORS_ORIGINS`.
- **Evidence is a URL, not an upload:** file storage adds security risk (malware, metadata that can identify the uploader) and deployment complexity.
- **Moderator accounts in the database, seeded from environment variables:** no hardcoded credentials, and a CLI for resets.

## 23. Limitations and future improvements

- No rate limiting on case-code lookups or submissions (add per-IP throttling at the proxy or with a library such as slowapi, without storing IPs long-term)
- Single moderator role; no audit log of who changed what
- JWTs cannot be revoked before they expire
- No reporter-facing web page (the API and Swagger are the reporter interface)
- Evidence files, with metadata stripping, as an optional future feature
- A per-report secret in addition to the case code, or two-way anonymous messaging so moderators can ask follow-up questions
- Database migrations (Alembic) and PostgreSQL for multi-instance deployments
- Optional Tor onion service for stronger network anonymity

## Live Demo

Dashboard: https://whistledrop-1-s77z.onrender.com/dashboard/

API Documentation: https://whistledrop-1-s77z.onrender.com/docs

## Run Locally

### 1. Clone the repository

```bash
git clone https://github.com/ShineKaninwal/whistledrop.git
cd whistledrop
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and configure the required settings.
Use a unique secret key and a strong moderator password.
Never commit `.env` or publish real passwords.

### 5. Create a moderator account

```powershell
python -m app.create_moderator --username admin
```

Follow the prompts to set the moderator password.

### 6. Start the application

```powershell
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/ in your browser.

## Demo Login

Username: `admin`

Password: Use the demo credentials provided separately by the project maintainer. For security, passwords are not stored in this public README.

## Contributing

1. Fork this repository.
2. Create a feature branch.
3. Make and test your changes.
4. Submit a pull request.

## Live Demo

Dashboard: https://whistledrop-1-s77z.onrender.com/dashboard/

API Documentation: https://whistledrop-1-s77z.onrender.com/docs

## Run Locally

### 1. Clone the repository

```bash
git clone https://github.com/ShineKaninwal/whistledrop.git
cd whistledrop
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and configure the required settings.
Use a unique secret key and a strong moderator password.
Never commit `.env` or publish real passwords.

### 5. Create a moderator account

```powershell
python -m app.create_moderator --username admin
```

Follow the prompts to set the moderator password.

### 6. Start the application

```powershell
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/ in your browser.

## Demo Login

Username: `admin`

Password: Use the demo credentials provided separately by the project maintainer. For security, passwords are not stored in this public README.

## Contributing

1. Fork this repository.
2. Create a feature branch.
3. Make and test your changes.
4. Submit a pull request.
