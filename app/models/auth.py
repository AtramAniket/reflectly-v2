from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user import utcnow


class LoginCode(Base):
	"""One-time email login code. Only a hash of the code is stored."""

	__tablename__ = "login_codes"

	id: Mapped[int] = mapped_column(primary_key=True)
	email: Mapped[str] = mapped_column(String(320), index=True)
	code_hash: Mapped[str] = mapped_column(String(64))
	attempts: Mapped[int] = mapped_column(Integer, default=0)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
	"""Opaque, rotating refresh token. Only a hash of the token is stored."""

	__tablename__ = "refresh_tokens"

	id: Mapped[int] = mapped_column(primary_key=True)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
	token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
