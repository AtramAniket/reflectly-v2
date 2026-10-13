from sqlalchemy import func, select

from app.models.user import User
from tests.conftest import API, auth_header, wrong_code

EMAIL = "alice@example.com"


def count_users(db, email=None):
	stmt = select(func.count(User.id))
	if email:
		stmt = stmt.where(User.email == email)
	return db.scalar(stmt)


def test_request_code_does_not_create_user(client, db):
	assert client.post(f"{API}/request-code", json={"email": EMAIL}).status_code == 200
	assert count_users(db) == 0


def test_wrong_code_does_not_create_user(client, mailer, db):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	r = client.post(
		f"{API}/verify-code",
		json={"email": EMAIL, "code": wrong_code(mailer.last_code())},
	)
	assert r.status_code == 400
	assert count_users(db) == 0


def test_correct_code_creates_user(login, db):
	login(EMAIL)
	user = db.scalar(select(User).where(User.email == EMAIL))
	assert count_users(db) == 1
	assert user.is_active is True
	assert user.created_at is not None
	assert user.last_login_at is not None


def test_me_returns_new_user(login, client):
	tokens = login(EMAIL)
	r = client.get(f"{API}/me", headers=auth_header(tokens["access_token"]))
	assert r.status_code == 200
	assert r.json()["email"] == EMAIL


def test_repeat_login_reuses_user_and_updates_last_login(login, db):
	login(EMAIL)
	first = db.scalar(select(User).where(User.email == EMAIL))
	first_id, first_login = first.id, first.last_login_at
	db.expire_all()

	login(EMAIL)
	db.expire_all()
	again = db.scalar(select(User).where(User.email == EMAIL))
	assert count_users(db) == 1
	assert again.id == first_id
	assert again.last_login_at > first_login


def test_email_is_normalized_to_lowercase(login, db):
	login("Alice@Example.COM")
	assert db.scalar(select(User.email)) == "alice@example.com"
	login("ALICE@EXAMPLE.COM")
	assert count_users(db) == 1


def test_code_for_one_email_cannot_log_in_another(client, mailer, db):
	client.post(f"{API}/request-code", json={"email": "a@example.com"})
	r = client.post(
		f"{API}/verify-code",
		json={"email": "b@example.com", "code": mailer.last_code("a@example.com")},
	)
	assert r.status_code == 400
	assert count_users(db, "b@example.com") == 0


def test_disabled_user_cannot_log_in(login, client, mailer, db):
	login(EMAIL)
	user = db.scalar(select(User).where(User.email == EMAIL))
	user.is_active = False
	db.commit()

	client.post(f"{API}/request-code", json={"email": EMAIL})
	r = client.post(
		f"{API}/verify-code", json={"email": EMAIL, "code": mailer.last_code()}
	)
	assert r.status_code == 403
	assert "access_token" not in r.json()


def test_disabled_user_existing_access_token_rejected(login, client, db):
	tokens = login(EMAIL)
	user = db.scalar(select(User).where(User.email == EMAIL))
	user.is_active = False
	db.commit()

	r = client.get(f"{API}/me", headers=auth_header(tokens["access_token"]))
	assert r.status_code == 401


def test_invalid_email_rejected(client):
	assert client.post(f"{API}/request-code", json={"email": "nope"}).status_code == 422


def test_malformed_code_rejected(client):
	for bad in ("12345", "1234567", "abcdef", ""):
		r = client.post(f"{API}/verify-code", json={"email": EMAIL, "code": bad})
		assert r.status_code == 422, bad
