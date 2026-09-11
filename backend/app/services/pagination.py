"""Cursor-paginering med stabil sekundærsortering på ID.

Standard 50, maks 100. Markøren bærer sorteringsnøkkelen og ID-en til siste rad
på siden, slik at neste side ikke hopper over eller gjentar rader når nye rader
skrives inn under pagineringen.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from typing import Any

import sqlalchemy as sa

from app.errors import invalid_cursor

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


def page_size(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_PAGE_SIZE
    return max(1, min(limit, MAX_PAGE_SIZE))


def encode_cursor(scope: str, key: str, row_id: uuid.UUID) -> str:
    payload = json.dumps({"s": scope, "k": key, "i": str(row_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, scope: str) -> tuple[str, uuid.UUID]:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if payload["s"] != scope:
            raise ValueError("cursor belongs to another ordering")
        return payload["k"], uuid.UUID(payload["i"])
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise invalid_cursor() from exc


def keyset(expression, row_id_column, key: Any, row_id: uuid.UUID, descending: bool):
    """Neste side starter etter (sorteringsnøkkel, ID); ID-en gjør rekkefølgen stabil."""
    ahead = expression < key if descending else expression > key
    return sa.or_(ahead, sa.and_(expression == key, row_id_column > row_id))
