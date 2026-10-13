import hmac
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.models.auth import LoginCode, RefreshToken
from app.models.user import User
from app.schemas.auth import TokenOut
from app.services.mailer import Mailer

RATE_LIMIT_WINDOW = timedelta(minutes=10)


def _now() -> datetime:
	return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
	return email.strip().lower()


def request_login_code(db: Session, email: str, mailer: Mailer) -> None:
	email = normalize_email(email)
	now = _now()

	recent = db.scalar(
		select(func.count(LoginCode.id)).where(
			LoginCode.email == email,
			LoginCode.created_at > now - RATE_LIMIT_WINDOW,
		)
	)
	if recent >= settings.login_code_max_requests_per_window:
		raise HTTPException(
			status.HTTP_429_TOO_MANY_REQUESTS,
			"Too many code requests. Please try again later.",
		)

	# Only the newest code is ever valid.
	db.execute(
		update(LoginCode)
		.where(LoginCode.email == email, LoginCode.used_at.is_(None))
		.values(used_at=now)
	)

	code = security.generate_login_code()
	db.add(
		LoginCode(
			email=email,
			code_hash=security.hash_login_code(email, code),
			expires_at=now + timedelta(minutes=settings.login_code_expire_minutes),
		)
	)

	# Send before committing so a mail failure doesn't burn a rate-limit slot.
	try:
		mailer.send(
			to=email,
			subject=f"Your {settings.mail_sender_name} login code: {code}",
			text=(
				f"Your login code is {code}\n\n"
				f"It expires in {settings.login_code_expire_minutes} minutes. "
				"If you didn't request this, you can ignore this email."
			),
		)
	except Exception:
		db.rollback()
		raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not send email.")

	db.commit()


def verify_login_code(db: Session, email: str, code: str) -> TokenOut:
	email = normalize_email(email)
	now = _now()
	invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired code.")

	login_code = db.scalar(
		select(LoginCode)
		.where(
			LoginCode.email == email,
			LoginCode.used_at.is_(None),
			LoginCode.expires_at > now,
		)
		.order_by(LoginCode.created_at.desc())
		.limit(1)
		.with_for_update()
	)
	if login_code is None or login_code.attempts >= settings.login_code_max_attempts:
		raise invalid

	login_code.attempts += 1
	if not hmac.compare_digest(login_code.code_hash, security.hash_login_code(email, code)):
		db.commit()  # persist the failed attempt
		raise invalid

	login_code.used_at = now

	user = _get_or_create_user(db, email)
	if not user.is_active:
		db.commit()
		raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled.")
	user.last_login_at = now

	tokens = _issue_tokens(db, user)
	db.commit()
	return tokens


def refresh_tokens(db: Session, refresh_token: str) -> TokenOut:
	now = _now()
	invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.")

	stored = db.scalar(
		select(RefreshToken)
		.where(RefreshToken.token_hash == security.hash_refresh_token(refresh_token))
		.with_for_update()
	)
	if stored is None:
		raise invalid

	if stored.revoked_at is not None:
		# A rotated token was replayed: assume theft and kill the whole family.
		_revoke_all_for_user(db, stored.user_id, now)
		db.commit()
		raise invalid

	if stored.expires_at <= now:
		raise invalid

	user = db.get(User, stored.user_id)
	if user is None or not user.is_active:
		raise invalid

	stored.revoked_at = now
	tokens = _issue_tokens(db, user)
	db.commit()
	return tokens


def logout(db: Session, refresh_token: str) -> None:
	stored = db.scalar(
		select(RefreshToken).where(
			RefreshToken.token_hash == security.hash_refresh_token(refresh_token)
		)
	)
	if stored is not None and stored.revoked_at is None:
		stored.revoked_at = _now()
		db.commit()


def _find_user(db: Session, email: str) -> User | None:
	return db.scalar(select(User).where(User.email == email))


def _get_or_create_user(db: Session, email: str) -> User:
	"""Find the user, creating them on first login.

	The insert runs in a savepoint so that if a concurrent request creates the
	same user between our lookup and insert, the unique index on email rejects
	ours and we fall back to the row that won instead of failing the login.
	"""
	user = _find_user(db, email)
	if user is not None:
		return user

	try:
		with db.begin_nested():
			user = User(email=email)
			db.add(user)
			db.flush()
		return user
	except IntegrityError:
		user = _find_user(db, email)
		if user is None:
			raise
		return user


def _issue_tokens(db: Session, user: User) -> TokenOut:
	refresh_token = security.generate_refresh_token()
	db.add(
		RefreshToken(
			user_id=user.id,
			token_hash=security.hash_refresh_token(refresh_token),
			expires_at=_now() + timedelta(days=settings.refresh_token_expire_days),
		)
	)
	return TokenOut(
		access_token=security.create_access_token(user.id),
		refresh_token=refresh_token,
		expires_in=settings.access_token_expire_minutes * 60,
	)


def _revoke_all_for_user(db: Session, user_id: int, now: datetime) -> None:
	db.execute(
		update(RefreshToken)
		.where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
		.values(revoked_at=now)
	)
