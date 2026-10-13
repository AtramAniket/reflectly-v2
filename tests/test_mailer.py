import pytest

from app.core.config import settings
from app.main import app
from app.services import mailer as mailer_module
from app.services.mailer import BrevoMailer, ConsoleMailer, get_mailer
from sqlalchemy import func, select

from app.models.auth import LoginCode
from tests.conftest import API, FailingMailer


class FakeResponse:
	def __init__(self, status_code=201, text="{}"):
		self.status_code = status_code
		self.text = text


def test_console_mailer_prints_to_terminal(capsys):
	ConsoleMailer().send("a@example.com", "Hello", "Your login code is 123456")
	out = capsys.readouterr().out
	assert "a@example.com" in out and "123456" in out


def test_get_mailer_dev_vs_prod(monkeypatch):
	monkeypatch.setattr(settings, "environment", "development")
	assert isinstance(get_mailer(), ConsoleMailer)
	monkeypatch.setattr(settings, "environment", "production")
	assert isinstance(get_mailer(), BrevoMailer)


def test_brevo_mailer_request_shape(monkeypatch):
	captured = {}

	def fake_post(url, headers, json, timeout):
		captured.update(url=url, headers=headers, json=json, timeout=timeout)
		return FakeResponse(201)

	monkeypatch.setattr(mailer_module.httpx, "post", fake_post)
	BrevoMailer().send("to@example.com", "Subject", "Body")

	assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
	assert captured["headers"]["api-key"] == settings.brevo_api_key
	assert captured["json"]["sender"]["email"] == settings.mail_client_addr
	assert captured["json"]["to"] == [{"email": "to@example.com"}]
	assert captured["json"]["subject"] == "Subject"
	assert captured["json"]["textContent"] == "Body"


def test_brevo_mailer_raises_on_provider_error(monkeypatch):
	monkeypatch.setattr(
		mailer_module.httpx, "post", lambda *a, **k: FakeResponse(401, "unauthorized")
	)
	with pytest.raises(RuntimeError):
		BrevoMailer().send("to@example.com", "S", "B")


def test_mail_failure_returns_502_and_stores_no_code(client, db):
	app.dependency_overrides[get_mailer] = lambda: FailingMailer()
	r = client.post(f"{API}/request-code", json={"email": "a@example.com"})
	assert r.status_code == 502
	assert db.scalar(select(func.count(LoginCode.id))) == 0
