"""Feilkontrakten for /v2: `code`, trygg `message`, `field_errors`, `retryable`, `request_id`.

Meldingene er faste tekster. Ingen OCR-tekst, ID-er, tokens eller stacktrace
sendes til klienten.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(frozen=True)
class FieldError:
    field: str
    code: str
    message: str


class ApiError(Exception):
    """Feil som serialiseres i v2-formatet."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        field_errors: list[FieldError] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors or []
        self.retryable = retryable


def not_found() -> ApiError:
    """Samme svar for ukjent og fremmed ID, slik at eierskap ikke lekker."""
    return ApiError(404, "NOT_FOUND", "Fant ikke ressursen.")


def invalid_cursor() -> ApiError:
    return ApiError(
        400,
        "INVALID_CURSOR",
        "Pagineringsmarkøren er ugyldig. Hent listen på nytt.",
        [FieldError("cursor", "invalid_cursor", "Markøren kan ikke brukes.")],
    )


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "field_errors": [
                {"field": error.field, "code": error.code, "message": error.message}
                for error in exc.field_errors
            ],
            "retryable": exc.retryable,
            "request_id": new_request_id(),
        },
    )
