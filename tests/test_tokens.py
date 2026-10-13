from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select, update

from app.core import security
from app.core.config import settings
from app.models.auth import RefreshToken
from tests.conftest import API, auth_header


def test_refresh_rotates_tokens(login, client):
	t1 = login()
	r = client.post(f"{API}/refresh", json={"refresh_token": t1["refresh_token"]})
	assert r.status_code == 200
	t2 = r.json()
	assert t2["refresh_token"] != t1["refresh_token"]
	assert client.get(f"{API}/me", headers=auth_header(t2["access_token"])).status_code == 200


def test_refresh_token_stored_hashed(login, db):
	t = login()
	stored = db.scalars(select(RefreshToken)).all()
	assert len(stored) == 1
	assert stored[0].token_hash != t["refresh_token"]


def test_replayed_refresh_token_revokes_family(login, client):
	t1 = login()
	t2 = client.post(f"{API}/refresh", json={"refresh_token": t1["refresh_token"]}).json()

	replay = client.post(f"{API}/refresh", json={"refresh_token": t1["refresh_token"]})
	assert replay.status_code == 401

	# The legitimate newer token is revoked too (theft assumed).
	after = client.post(f"{API}/refresh", json={"refresh_token": t2["refresh_token"]})
	assert after.status_code == 401


def test_logout_revokes_refresh_token(login, client):
	t = login()
	assert client.post(f"{API}/logout", json={"refresh_token": t["refresh_token"]}).status_code == 200
	r = client.post(f"{API}/refresh", json={"refresh_token": t["refresh_token"]})
	assert r.status_code == 401


def test_logout_with_unknown_token_is_harmless(client):
	r = client.post(f"{API}/logout", json={"refresh_token": "does-not-exist"})
	assert r.status_code == 200


def test_unknown_refresh_token_rejected(client):
	r = client.post(f"{API}/refresh", json={"refresh_token": "does-not-exist"})
	assert r.status_code == 401


def test_expired_refresh_token_rejected(login, client, db):
	t = login()
	db.execute(
		update(RefreshToken).values(
			expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
		)
	)
	db.commit()
	r = client.post(f"{API}/refresh", json={"refresh_token": t["refresh_token"]})
	assert r.status_code == 401


def test_me_requires_authentication(client):
	assert client.get(f"{API}/me").status_code == 401


def test_me_rejects_garbage_token(client):
	assert client.get(f"{API}/me", headers=auth_header("not.a.jwt")).status_code == 401


def test_me_rejects_expired_access_token(login, client):
	login()
	now = datetime.now(timezone.utc)
	expired = jwt.encode(
		{"sub": "1", "type": "access", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
		settings.secret_key,
		algorithm=settings.algorithm,
	)
	assert client.get(f"{API}/me", headers=auth_header(expired)).status_code == 401


def test_me_rejects_token_signed_with_wrong_key(login, client):
	login()
	forged = jwt.encode(
		{"sub": "1", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
		"some-other-secret-key-0123456789abcdef",
		algorithm=settings.algorithm,
	)
	assert client.get(f"{API}/me", headers=auth_header(forged)).status_code == 401


def test_me_rejects_non_access_token_type(login, client):
	login()
	other = jwt.encode(
		{"sub": "1", "type": "refresh", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
		settings.secret_key,
		algorithm=settings.algorithm,
	)
	assert client.get(f"{API}/me", headers=auth_header(other)).status_code == 401


def test_access_token_roundtrip():
	assert security.decode_access_token(security.create_access_token(42)) == 42


def test_token_response_shape(login):
	t = login()
	assert t["token_type"] == "bearer"
	assert t["expires_in"] == settings.access_token_expire_minutes * 60
