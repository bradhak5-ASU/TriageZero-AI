"""Firebase ID-token verification for human dashboard access.

Two separate credential kinds reach this backend and they must never be
confused:

* **Humans** sign in through Firebase in the browser and send a short-lived
  Firebase **ID token**. That token is verified here, against Google's public
  keys, using Firebase Admin.
* **Machines** (the NovaCart Playwright reporter, Cloud Build) send a static
  high-entropy **ingestion token**. That path is unchanged and never touches
  Firebase.

Nothing in this module runs at import time. The Admin SDK is imported and
initialized lazily, on first verification, using Application Default
Credentials — so the backend imports, starts, and tests without any Firebase
credential present and without a service-account JSON file in the repository.

Tests inject a fake verifier through ``set_token_verifier`` and therefore never
contact Firebase or the network.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError


@dataclass(frozen=True)
class VerifiedUser:
    """The identity claims we are willing to act on.

    Deliberately small: TriageZero's signed-in dashboard is one shared,
    sanitized demo workspace, so nothing here is used for per-user data
    partitioning yet.
    """

    uid: str
    email: str | None = None
    email_verified: bool = False


class FirebaseAuthError(Exception):
    """Raised when an ID token is absent, malformed, expired, or not ours."""


#: Signature of a token verifier: raw ID token -> VerifiedUser.
TokenVerifier = Callable[[str], VerifiedUser]

_verifier: TokenVerifier | None = None
_app: Any | None = None


def set_token_verifier(verifier: TokenVerifier | None) -> None:
    """Install a verifier. Tests use this to stay offline."""
    global _verifier
    _verifier = verifier


def reset_firebase_app() -> None:
    """Drop the cached Admin app (tests and config changes)."""
    global _app
    _app = None


def _firebase_app() -> Any:
    """Initialize Firebase Admin lazily, with ADC and an explicit project id.

    An explicit project id matters: ID-token verification checks the audience,
    so a mismatched or inferred project would silently accept nothing.
    """
    global _app
    if _app is not None:
        return _app

    settings = get_settings()
    project_id = settings.firebase_project_id or settings.google_cloud_project
    if not project_id:
        raise FirebaseAuthError("Firebase project id is not configured")

    try:
        import firebase_admin
    except ImportError as exc:  # pragma: no cover - dependency ships in the image
        raise FirebaseAuthError("firebase-admin is not installed") from exc

    try:
        _app = firebase_admin.get_app()
    except ValueError:
        # Application Default Credentials only — never a checked-in key file.
        _app = firebase_admin.initialize_app(options={"projectId": project_id})
    return _app


def _default_verifier(id_token: str) -> VerifiedUser:
    """Verify a Firebase ID token against Google's public keys."""
    app = _firebase_app()
    try:
        from firebase_admin import auth as firebase_auth
    except ImportError as exc:  # pragma: no cover
        raise FirebaseAuthError("firebase-admin is not installed") from exc

    try:
        # check_revoked would add a Firebase round trip per request; the short
        # token lifetime is the mitigation for the demo workspace.
        claims = firebase_auth.verify_id_token(id_token, app=app)
    except Exception as exc:  # noqa: BLE001 - every failure is an auth failure
        # The SDK's message can echo token contents, so it is never surfaced.
        raise FirebaseAuthError("Firebase ID token verification failed") from exc

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        raise FirebaseAuthError("Firebase ID token has no subject")
    return VerifiedUser(
        uid=str(uid),
        email=claims.get("email"),
        email_verified=bool(claims.get("email_verified", False)),
    )


def verify_id_token(id_token: str) -> VerifiedUser:
    """Verify an ID token using the installed (or default) verifier."""
    verifier = _verifier or _default_verifier
    return verifier(id_token)


def firebase_enabled() -> bool:
    settings = get_settings()
    if not settings.firebase_auth_enabled:
        return False
    # A fake verifier means tests have taken over; treat that as enabled.
    if _verifier is not None:
        return True
    return bool(settings.firebase_project_id or settings.google_cloud_project)


def authentication_error(message: str = "Invalid or expired sign-in.") -> AppError:
    """401 — the credential itself did not authenticate."""
    return AppError("authentication_failed", message, status_code=401)
