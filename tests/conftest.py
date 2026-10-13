"""Test configuration.

Tests run against a dedicated `<dbname>_test` Postgres database (created on
demand) with fake secrets, so they never touch dev data or the real Brevo API.
The environment must be set up before any `app.*` module is imported.
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import pytest
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

_ROOT = Path(__file__).resolve().parent.parent
_base_url = make_url(
	os.environ.get("DATABASE_URL") or dotenv_values(_ROOT / ".env")["DATABASE_URL"]
)
_test_db_name = _base_url.database
if not _test_db_name.endswith("_test"):
	_test_db_name += "_test"
_test_url = _base_url.set(database=_test_db_name)

os.environ.update(
	DATABASE_URL=_test_url.render_as_string(hide_password=False),
	SECRET_KEY="test-secret-key-not-for-production-use-0123456789",
	ALGORITHM="HS256",
	ACCESS_TOKEN_EXPIRE_MINUTES="15",
	MAIL_CLIENT_ADDR="noreply@test.example",
	BREVO_API_KEY="test-brevo-key",
	ENVIRONMENT="development",
	DEBUG="false",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import auth as _auth_models, user as _user_models  # noqa: E402,F401
from app.services.mailer import get_mailer  # noqa: E402

API = "/api/v2/auth"


@dataclass
class SentMail:
	to: str
	subject: str
	text: str

	@property
	def code(self) -> str:
		return re.search(r"login code is (\d{6})", self.text).group(1)


class FakeMailer:
	def __init__(self) -> None:
		self.sent: list[SentMail] = []

	def send(self, to: str, subject: str, text: str) -> None:
		self.sent.append(SentMail(to, subject, text))

	def last_code(self, to: str | None = None) -> str:
		# The service normalizes addresses to lowercase before sending.
		mails = [m for m in self.sent if to is None or m.to == to.strip().lower()]
		return mails[-1].code


class FailingMailer:
	def send(self, to: str, subject: str, text: str) -> None:
		raise RuntimeError("provider down")


@pytest.fixture(scope="session", autouse=True)
def _test_database():
	conn = psycopg2.connect(
		host=_base_url.host,
		port=_base_url.port,
		user=_base_url.username,
		password=_base_url.password,
		dbname="postgres",
	)
	conn.autocommit = True
	with conn.cursor() as cur:
		cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (_test_db_name,))
		if cur.fetchone() is None:
			cur.execute(f'CREATE DATABASE "{_test_db_name}"')
	conn.close()

	Base.metadata.create_all(engine)
	yield
	engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(_test_database):
	with engine.begin() as conn:
		conn.execute(
			text("TRUNCATE users, login_codes, refresh_tokens RESTART IDENTITY CASCADE")
		)
	yield


@pytest.fixture
def mailer():
	fake = FakeMailer()
	app.dependency_overrides[get_mailer] = lambda: fake
	yield fake
	app.dependency_overrides.pop(get_mailer, None)


@pytest.fixture
def client(mailer):
	return TestClient(app)


@pytest.fixture
def db():
	session = SessionLocal()
	yield session
	session.close()


@pytest.fixture
def login(client, mailer):
	"""Run the full request-code -> verify-code flow and return the token dict."""

	def _login(email: str = "alice@example.com") -> dict:
		assert client.post(f"{API}/request-code", json={"email": email}).status_code == 200
		r = client.post(
			f"{API}/verify-code", json={"email": email, "code": mailer.last_code(email)}
		)
		assert r.status_code == 200, r.text
		return r.json()

	return _login


def auth_header(access_token: str) -> dict:
	return {"Authorization": f"Bearer {access_token}"}


def wrong_code(code: str) -> str:
	return "000000" if code != "000000" else "111111"
