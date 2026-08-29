"""Request dependencies: database session and API authentication.

Two independent credential paths, deliberately kept apart:

* **Machine ingestion** — the NovaCart Playwright reporter and Cloud Build send
  the static ``INGESTION_API_TOKEN``. It can submit failure packages and
  nothing else: it can never read or mutate investigations.
* **Human dashboard** — a signed-in user sends a Firebase **ID token**, which
  is verified against Google's public keys. ``DASHBOARD_API_TOKEN`` remains
  accepted as a break-glass/scripting credential.

Local development stays open by default (``API_AUTH_REQUIRED=false``);
staging and production fail closed via configuration validation.
"""

import secrets
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.firebase_auth import (
    FirebaseAuthError,
    VerifiedUser,
    authentication_error,
    firebase_enabled,
    verify_id_token,
)
from app.db.session import get_session

SessionDep = Annotated[Session, Depends(get_session)]


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AppError(
            "authentication_required",
            "A bearer token is required for this API operation.",
            status_code=401,
        )
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise AppError(
            "authentication_required",
            "Authorization must use the Bearer scheme.",
            status_code=401,
        )
    return token.strip()


def _matches_static_token(supplied: str, expected: str) -> bool:
    # constant-time, and an unset token can never be matched by an empty string
    return bool(expected) and secrets.compare_digest(supplied, expected)


def _authenticate(
    authorization: str | None, *, allow_ingestion: bool
) -> VerifiedUser | None:
    """Authenticate a request for one scope.

    Returns the signed-in user when a Firebase ID token was used, or ``None``
    when a static service token was used (or auth is disabled locally).
    """
    settings = get_settings()
    if not settings.api_auth_required:
        return None

    supplied = _bearer_token(authorization)

    # 1. static service tokens — unchanged behavior
    if _matches_static_token(supplied, settings.dashboard_api_token.get_secret_value()):
        return None
    if allow_ingestion and _matches_static_token(
        supplied, settings.ingestion_api_token.get_secret_value()
    ):
        return None

    # 2. a RECOGNIZED machine credential on a route it may not use is an
    #    authorization failure (403), not an authentication failure — it must
    #    not fall through to Firebase and come back as 401.
    if not allow_ingestion and _matches_static_token(
        supplied, settings.ingestion_api_token.get_secret_value()
    ):
        raise AppError(
            "forbidden",
            "The ingestion token cannot be used for dashboard operations.",
            status_code=403,
        )

    # 3. human sign-in, only when Firebase is configured
    if firebase_enabled():
        try:
            return verify_id_token(supplied)
        except FirebaseAuthError as exc:
            # the credential failed to authenticate → 401, not 403
            raise authentication_error() from exc

    # 4. a well-formed credential that is not recognized at all.
    raise AppError(
        "forbidden",
        "The supplied bearer token is not authorized for this operation.",
        status_code=403,
    )


def require_ingestion_auth(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> VerifiedUser | None:
    """Failure-package submission: machines, or a signed-in human using the
    manual Ingest page."""
    return _authenticate(authorization, allow_ingestion=True)


def require_dashboard_auth(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> VerifiedUser | None:
    """Dashboard/management APIs. The ingestion token is NOT accepted here."""
    return _authenticate(authorization, allow_ingestion=False)


IngestionAuthDep = Annotated[VerifiedUser | None, Depends(require_ingestion_auth)]
DashboardAuthDep = Annotated[VerifiedUser | None, Depends(require_dashboard_auth)]
