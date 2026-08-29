import secrets
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
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


def _require_token(authorization: str | None, *, allow_ingestion: bool) -> None:
    settings = get_settings()
    if not settings.api_auth_required:
        return

    supplied = _bearer_token(authorization)
    accepted = [settings.dashboard_api_token.get_secret_value()]
    if allow_ingestion:
        accepted.append(settings.ingestion_api_token.get_secret_value())
    if not any(secrets.compare_digest(supplied, expected) for expected in accepted):
        raise AppError(
            "forbidden",
            "The supplied bearer token is not authorized for this operation.",
            status_code=403,
        )


def require_ingestion_auth(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    _require_token(authorization, allow_ingestion=True)


def require_dashboard_auth(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    _require_token(authorization, allow_ingestion=False)


IngestionAuthDep = Annotated[None, Depends(require_ingestion_auth)]
DashboardAuthDep = Annotated[None, Depends(require_dashboard_auth)]
