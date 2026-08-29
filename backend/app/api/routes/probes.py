"""Container probes for Cloud Run.

Separate from `/api/v1/health`, which is the dashboard's rich status view: it
queries several tables, computes hourly volume buckets and reports provider
state. That is the right payload for a human looking at the Command Center and
the wrong one for a probe fired every few seconds - it would put avoidable load
on Cloud SQL and could report a container unhealthy because a *feature* is
degraded rather than because the process is broken.

    /api/v1/livez   process is alive. No database, no dependencies. Restarting
                    the container is the only thing that could fix a failure
                    here, which is exactly what a liveness probe is for.

    /api/v1/readyz  this instance can serve requests: the database answers and
                    the investigations table exists. Used as the startup probe,
                    so a revision whose DATABASE_URL or Cloud SQL connection is
                    wrong fails to come up instead of serving 500s.

Both are deliberately free of authentication - a platform probe carries no
credentials - so neither may disclose anything. Their bodies are a fixed
status string and, on failure, a generic reason: never a URL, a driver
message, a hostname, or any investigation content.
"""

from fastapi import APIRouter, Response
from sqlalchemy import inspect, text

from app.core.logging import log_event
from app.db.models import InvestigationRecord
from app.db.session import new_session

router = APIRouter()

TABLE = InvestigationRecord.__tablename__


@router.get("/livez", include_in_schema=False)
def livez() -> dict[str, str]:
    """Liveness: the process is running and can serve HTTP."""
    return {"status": "alive"}


@router.get("/readyz", include_in_schema=False)
def readyz(response: Response) -> dict[str, str]:
    """Readiness: the datastore is reachable and migrated.

    A failure returns 503 so Cloud Run holds traffic off this instance rather
    than sending requests that would fail one layer deeper.
    """
    # Opening the session is itself a failure mode - a bad DATABASE_URL or an
    # unreachable Cloud SQL instance fails here, before any query - so it must
    # be inside the guard, not before it.
    session = None
    try:
        session = new_session()
        session.execute(text("SELECT 1"))
        if not inspect(session.get_bind()).has_table(TABLE):
            response.status_code = 503
            # The operator finds the detail in the logs; the response body
            # stays generic because this endpoint is unauthenticated.
            log_event("readiness check failed", reason="schema_not_initialized")
            return {"status": "not_ready", "reason": "schema_not_initialized"}
        return {"status": "ready"}
    except Exception as exc:  # noqa: BLE001 - a probe must never raise
        response.status_code = 503
        log_event(
            "readiness check failed",
            reason="datastore_unavailable",
            error=type(exc).__name__,
        )
        return {"status": "not_ready", "reason": "datastore_unavailable"}
    finally:
        if session is not None:
            session.close()
