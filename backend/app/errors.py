"""Feilkontrakten for /v2: `code`, trygg `message`, `field_errors`, `retryable`, `request_id`.

Meldingene er faste tekster. Ingen OCR-tekst, ID-er, tokens eller stacktrace
sendes til klienten.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
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
        extra: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field_errors = field_errors or []
        self.retryable = retryable
        # Trygge, maskinlesbare tillegg som `current_version`. Aldri OCR-tekst,
        # ID-er, tokens eller stacktrace.
        self.extra = extra or {}


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


def unauthenticated() -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", "Du er ikke innlogget.")


def email_not_verified() -> ApiError:
    return ApiError(401, "EMAIL_NOT_VERIFIED", "E-postadressen er ikke bekreftet.")


_RESET_VALIDATION_PATHS = frozenset(
    {
        "/auth/password-reset/request",
        "/auth/password-reset/complete",
    }
)


def api_error_from_request_validation(exc: RequestValidationError) -> ApiError:
    """C00 for nye reset-ruter. `input`/`ctx` og tokens tas ikke med."""
    field_errors: list[FieldError] = []
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", ()) if part != "body"]
        field = ".".join(loc) if loc else "body"
        error_type = str(error.get("type", "invalid"))
        if error_type == "missing":
            field_errors.append(FieldError(field, "required", "Feltet mangler."))
        else:
            field_errors.append(FieldError(field, "invalid", "Feltet er ugyldig."))
    return ApiError(
        400,
        "VALIDATION_ERROR",
        "Forespørselen er ugyldig.",
        field_errors,
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
            **exc.extra,
        },
    )


async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    if request.url.path in _RESET_VALIDATION_PATHS:
        return await api_error_handler(request, api_error_from_request_validation(exc))
    return await request_validation_exception_handler(request, exc)
