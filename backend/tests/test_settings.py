"""S09-A: produksjon avviser usikker JWT-hemmelighet."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_the_placeholder_jwt_secret():
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(environment="production", jwt_secret="change-me-in-production")


def test_production_rejects_an_empty_jwt_secret():
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(environment="production", jwt_secret="")


def test_prislapp_env_production_rejects_the_placeholder_secret(monkeypatch):
    monkeypatch.setenv("PRISLAPP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")
    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None)


def test_development_allows_the_placeholder_jwt_secret():
    settings = Settings(environment="development", jwt_secret="change-me-in-production")
    assert settings.environment == "development"
