from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
	MessageOut,
	RefreshIn,
	RequestCodeIn,
	TokenOut,
	UserOut,
	VerifyCodeIn,
)
from app.services import auth as auth_service
from app.services.mailer import Mailer, get_mailer

router = APIRouter(prefix="/auth", tags=["auth"])

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
	credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
	db: Session = Depends(get_db),
) -> User:
	unauthorized = HTTPException(
		status.HTTP_401_UNAUTHORIZED,
		"Not authenticated.",
		headers={"WWW-Authenticate": "Bearer"},
	)
	if credentials is None:
		raise unauthorized
	user_id = security.decode_access_token(credentials.credentials)
	if user_id is None:
		raise unauthorized
	user = db.get(User, user_id)
	if user is None or not user.is_active:
		raise unauthorized
	return user


@router.post("/request-code", response_model=MessageOut)
def request_code(
	body: RequestCodeIn,
	db: Session = Depends(get_db),
	mailer: Mailer = Depends(get_mailer),
):
	auth_service.request_login_code(db, body.email, mailer)
	# Same response whether or not the account exists (no user enumeration).
	return MessageOut(message="If the email is valid, a login code has been sent.")


@router.post("/verify-code", response_model=TokenOut)
def verify_code(body: VerifyCodeIn, db: Session = Depends(get_db)):
	return auth_service.verify_login_code(db, body.email, body.code)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
	return auth_service.refresh_tokens(db, body.refresh_token)


@router.post("/logout", response_model=MessageOut)
def logout(body: RefreshIn, db: Session = Depends(get_db)):
	auth_service.logout(db, body.refresh_token)
	return MessageOut(message="Logged out.")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
	return user
