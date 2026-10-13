import logging
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


class Mailer(Protocol):
	def send(self, to: str, subject: str, text: str) -> None: ...


class ConsoleMailer:
	"""Development mailer: prints the email to the terminal."""

	def send(self, to: str, subject: str, text: str) -> None:
		print(
			"\n" + "=" * 60
			+ f"\n[DEV MAIL] To: {to}\nSubject: {subject}\n\n{text}\n"
			+ "=" * 60 + "\n",
			flush=True,
		)


class BrevoMailer:
	"""Production mailer: Brevo transactional email API."""

	def send(self, to: str, subject: str, text: str) -> None:
		response = httpx.post(
			BREVO_SEND_URL,
			headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
			json={
				"sender": {"name": settings.mail_sender_name, "email": settings.mail_client_addr},
				"to": [{"email": to}],
				"subject": subject,
				"textContent": text,
			},
			timeout=10,
		)
		if response.status_code >= 400:
			# Don't leak provider details to the client; log for operators.
			logger.error("Brevo send failed: %s %s", response.status_code, response.text)
			raise RuntimeError("Failed to send email")


def get_mailer() -> Mailer:
	return BrevoMailer() if settings.is_production else ConsoleMailer()
