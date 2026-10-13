from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.main import app
from app.models.auth import RefreshToken
from app.models.user import User
from app.services import auth as auth_service
from tests.conftest import API

EMAIL = "race@example.com"


def test_get_or_create_user_survives_lost_race(db, monkeypatch):
	"""Another request creates the user between our lookup and our insert."""
	with SessionLocal() as other:
		other.add(User(email=EMAIL))
		other.commit()

	real_find = auth_service._find_user
	calls = {"n": 0}

	def find_once_missing(session, email):
		calls["n"] += 1
		return None if calls["n"] == 1 else real_find(session, email)

	monkeypatch.setattr(auth_service, "_find_user", find_once_missing)

	user = auth_service._get_or_create_user(db, EMAIL)
	db.commit()

	assert user.email == EMAIL
	assert db.scalar(select(func.count(User.id))) == 1
	assert calls["n"] == 2


def test_concurrent_verifies_of_same_code_yield_one_login(client, mailer, db):
	client.post(f"{API}/request-code", json={"email": EMAIL})
	code = mailer.last_code()

	def attempt(_):
		return TestClient(app).post(
			f"{API}/verify-code", json={"email": EMAIL, "code": code}
		).status_code

	with ThreadPoolExecutor(max_workers=6) as pool:
		statuses = list(pool.map(attempt, range(6)))

	assert statuses.count(200) == 1
	assert all(s in (200, 400) for s in statuses)
	assert db.scalar(select(func.count(User.id))) == 1
	assert db.scalar(select(func.count(RefreshToken.id))) == 1


def test_concurrent_first_logins_across_email_casings_create_single_user(
	client, mailer, db
):
	"""Casing variants normalize to one account; only the newest code is valid."""
	variants = [EMAIL, EMAIL.upper(), EMAIL.title()]
	for v in variants:
		client.post(f"{API}/request-code", json={"email": v})
	newest = mailer.sent[-1].code

	def attempt(v):
		return TestClient(app).post(
			f"{API}/verify-code", json={"email": v, "code": newest}
		).status_code

	with ThreadPoolExecutor(max_workers=len(variants)) as pool:
		statuses = list(pool.map(attempt, variants))

	assert statuses.count(200) == 1
	assert db.scalar(select(func.count(User.id))) == 1
