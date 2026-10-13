from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update

from app.core.config import settings
from app.models.auth import LoginCode
from tests.conftest import API, wrong_code

EMAIL = "alice@example.com"


def verify(client, code, email=EMAIL):
	return client.post(f"{API}/verify-code", json={"email": email, "code": code})


def test_code_is_emailed_and_six_digits(client, mailer):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	assert len(mailer.sent) == 1
	assert mailer.sent[0].to == EMAIL
	assert mailer.last_code().isdigit() and len(mailer.last_code()) == 6


def test_code_is_stored_hashed(client, mailer, db):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	row = db.scalar(select(LoginCode))
	assert row.code_hash != mailer.last_code()
	assert len(row.code_hash) == 64


def test_code_is_single_use(client, mailer):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	code = mailer.last_code()
	assert verify(client, code).status_code == 200
	assert verify(client, code).status_code == 400


def test_new_code_invalidates_previous(client, mailer):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	old = mailer.last_code()
	client.post(f"{API}/request-code", json={"email": EMAIL})
	new = mailer.last_code()
	if old != new:
		assert verify(client, old).status_code == 400
	assert verify(client, new).status_code == 200


def test_expired_code_rejected(client, mailer, db):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	db.execute(
		update(LoginCode).values(
			expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
		)
	)
	db.commit()
	assert verify(client, mailer.last_code()).status_code == 400


def test_lockout_after_max_attempts(client, mailer):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	good = mailer.last_code()
	for _ in range(settings.login_code_max_attempts):
		assert verify(client, wrong_code(good)).status_code == 400
	# Even the correct code is now refused.
	assert verify(client, good).status_code == 400


def test_failed_attempts_below_limit_do_not_lock(client, mailer):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	good = mailer.last_code()
	for _ in range(settings.login_code_max_attempts - 1):
		verify(client, wrong_code(good))
	assert verify(client, good).status_code == 200


def test_verify_without_request_is_rejected(client):
	assert verify(client, "123456").status_code == 400


def test_request_rate_limit(client):
	limit = settings.login_code_max_requests_per_window
	statuses = [
		client.post(f"{API}/request-code", json={"email": EMAIL}).status_code
		for _ in range(limit + 1)
	]
	assert statuses == [200] * limit + [429]


def test_rate_limit_is_per_email(client):
	for _ in range(settings.login_code_max_requests_per_window):
		client.post(f"{API}/request-code", json={"email": EMAIL})
	r = client.post(f"{API}/request-code", json={"email": "bob@example.com"})
	assert r.status_code == 200


def test_rate_limit_window_expires(client, db):
	for _ in range(settings.login_code_max_requests_per_window):
		client.post(f"{API}/request-code", json={"email": EMAIL})
	assert client.post(f"{API}/request-code", json={"email": EMAIL}).status_code == 429

	db.execute(text("UPDATE login_codes SET created_at = created_at - interval '11 minutes'"))
	db.commit()
	assert client.post(f"{API}/request-code", json={"email": EMAIL}).status_code == 200


def test_response_does_not_reveal_whether_account_exists(client, login):
	login("known@example.com")
	known = client.post(f"{API}/request-code", json={"email": "known@example.com"})
	unknown = client.post(f"{API}/request-code", json={"email": "unknown@example.com"})
	assert known.status_code == unknown.status_code == 200
	assert known.json() == unknown.json()
