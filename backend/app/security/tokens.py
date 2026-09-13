"""Hash av refresh- og reset-tokens. Rå verdier skal ikke logges."""

from __future__ import annotations

import hashlib
import hmac

from app.config import settings


def hash_secret(raw: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()
