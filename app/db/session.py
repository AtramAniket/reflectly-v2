from collections.abc import Iterator

from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

engine = create_engine(settings.database_url, echo=settings.debug)

SessionLocal = sessionmaker(
	bind=engine,
	autoflush=False,
	autocommit=False,
)


def get_db() -> Iterator[Session]:
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()
