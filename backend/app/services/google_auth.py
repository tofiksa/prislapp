import uuid

from google.auth.transport import requests
from google.oauth2 import id_token

from app.config import settings


def verify_google_id_token(token: str) -> dict:
    if not settings.google_client_id:
        raise ValueError("Google Sign-In is not configured")
    return id_token.verify_oauth2_token(token, requests.Request(), settings.google_client_id)
