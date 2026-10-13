import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


def generate_login_code() -> str:
	"""Cryptographically random 6-digit code."""
	return f"{secrets.randbelow(1_000_000):06d}"


def hash_login_code(email: str, code: str) -> str:
	"""HMAC so a leaked DB row can't be brute-forced without the secret key."""
	return hmac.new(
		settings.secret_key.encode(),
		f"{email}:{code}".encode(),
		hashlib.sha256,
	).hexdigest()


def generate_refresh_token() -> str:
	return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user_id: int) -> str:
	now = datetime.now(timezone.utc)
	payload = {
		"sub": str(user_id),
		"iat": now,
		"exp": now + timedelta(minutes=settings.access_token_expire_minutes),
		"type": "access",
	}
	return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> int | None:
	"""Return the user id, or None if the token is invalid/expired."""
	try:
		payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
	except jwt.PyJWTError:
		return None
	if payload.get("type") != "access":
		return None
	try:
		return int(payload["sub"])
	except (KeyError, ValueError):
		return None
