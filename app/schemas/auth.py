from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RequestCodeIn(BaseModel):
	email: EmailStr


class VerifyCodeIn(BaseModel):
	email: EmailStr
	code: str = Field(pattern=r"^\d{6}$")


class RefreshIn(BaseModel):
	refresh_token: str


class TokenOut(BaseModel):
	access_token: str
	refresh_token: str
	token_type: str = "bearer"
	expires_in: int


class MessageOut(BaseModel):
	message: str


class UserOut(BaseModel):
	model_config = ConfigDict(from_attributes=True)

	id: int
	email: EmailStr
	created_at: datetime
	last_login_at: datetime | None
