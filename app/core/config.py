from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

	app_name: str = "Reflectly v2.0"

	api_prefix: str = "/api/v2"

	environment: Literal["development", "production"] = "development"

	secret_key: str

	database_url: str

	debug: bool = True

	algorithm: str

	access_token_expire_minutes: int = 15

	refresh_token_expire_days: int = 30

	login_code_expire_minutes: int = 10

	login_code_max_attempts: int = 5

	login_code_max_requests_per_window: int = 5

	mail_client_addr: str

	mail_client_pass: str | None = None

	mail_sender_name: str = "Reflectly"

	brevo_api_key: str


	model_config = SettingsConfigDict(
		env_file=".env",
		extra="ignore",
	)

	@property
	def is_production(self) -> bool:
		return self.environment == "production"

settings = Settings()
