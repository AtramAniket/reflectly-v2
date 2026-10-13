# Reflectly v2

FastAPI backend for Reflectly. Currently implements passwordless email authentication (one-time login codes, similar to Claude's login flow).

## Stack

- Python 3.12, FastAPI, Uvicorn
- PostgreSQL, SQLAlchemy 2, Alembic
- PyJWT for access tokens
- Brevo transactional email API (production), terminal output (development)

## Project layout

```
app/
├── main.py            FastAPI app, router registration
├── core/
│   ├── config.py      Settings loaded from .env
│   └── security.py    Login code + token generation, hashing, JWT
├── db/
│   ├── base.py        SQLAlchemy declarative Base
│   └── session.py     Engine, SessionLocal, get_db dependency
├── models/            User, LoginCode, RefreshToken
├── schemas/           Pydantic request/response models
├── services/
│   ├── auth.py        Auth business logic
│   └── mailer.py      ConsoleMailer (dev) / BrevoMailer (prod)
└── routes/
    └── auth.py        Auth endpoints + get_current_user dependency
alembic/               Database migrations
tests/                 pytest suite
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

| Variable | Description |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@localhost:5432/reflectly_v2` |
| `SECRET_KEY` | Long random string used for JWT signing and code hashing |
| `ALGORITHM` | JWT algorithm, e.g. `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime (default `15`) |
| `MAIL_CLIENT_ADDR` | Sender address. Must be a verified sender in Brevo |
| `BREVO_API_KEY` | Brevo API key (used when `ENVIRONMENT=production`) |
| `ENVIRONMENT` | `development` (default) or `production` |

Optional overrides: `REFRESH_TOKEN_EXPIRE_DAYS` (30), `LOGIN_CODE_EXPIRE_MINUTES` (10), `LOGIN_CODE_MAX_ATTEMPTS` (5), `LOGIN_CODE_MAX_REQUESTS_PER_WINDOW` (5), `MAIL_SENDER_NAME` (`Reflectly`).

Create the database, then run migrations and start the server:

```bash
createdb reflectly_v2
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive docs are served at `http://localhost:8000/docs`.

## Authentication

Passwordless: the user enters an email, receives a 6-digit code, and exchanges it for tokens. Unknown emails are registered automatically on first successful verification.

| Method | Path | Body | Description |
|---|---|---|---|
| POST | `/api/v2/auth/request-code` | `{email}` | Email a login code |
| POST | `/api/v2/auth/verify-code` | `{email, code}` | Exchange code for access + refresh tokens |
| POST | `/api/v2/auth/refresh` | `{refresh_token}` | Rotate refresh token, get new tokens |
| POST | `/api/v2/auth/logout` | `{refresh_token}` | Revoke a refresh token |
| GET | `/api/v2/auth/me` | | Current user (`Authorization: Bearer <access_token>`) |

### Email delivery

- **development**: emails are printed to the terminal running uvicorn. Nothing is sent.
- **production**: emails are sent through the Brevo API (`POST /v3/smtp/email`).

### Security notes

- Login codes and refresh tokens are stored hashed, never in plain text.
- Codes expire after 10 minutes, are single-use, and allow 5 verification attempts.
- Requesting a new code invalidates previous ones; requests are limited to 5 per 10 minutes per email.
- Refresh tokens rotate on every use. Replaying a rotated token revokes all of that user's refresh tokens.
- `request-code` responds identically for known and unknown emails.

## Testing

```bash
pytest
```

Tests run against a separate `<dbname>_test` Postgres database (created automatically from your `DATABASE_URL`, with tables built from the models). They use fake secrets and an in-memory mailer, so dev data and the real Brevo API are never touched. Tables are truncated between tests.

| File | Covers |
|---|---|
| `test_user_creation.py` | When users are created, re-login, email normalization, disabled accounts, validation |
| `test_login_codes.py` | Hashing, single use, expiry, attempt lockout, rate limiting |
| `test_tokens.py` | Refresh rotation, replay detection, logout, JWT validation |
| `test_mailer.py` | Console vs Brevo selection, Brevo request shape, provider failure handling |
| `test_concurrency.py` | Concurrent first-login and double-submit races |

## Migrations

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
alembic downgrade -1
```

## License

GPL-3.0. See [LICENSE](LICENSE).
