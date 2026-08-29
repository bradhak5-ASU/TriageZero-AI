from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import health, investigations
from app.core.config import get_settings
from app.core.errors import error_body, register_error_handlers
from app.core.logging import configure_logging, log_event
from app.db.session import init_db
from app.services.processing import recover_pending


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from app.services.processing import dispatcher

    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()
    if hasattr(dispatcher, "bind_loop"):
        dispatcher.bind_loop(asyncio.get_running_loop())
    recovered = recover_pending()
    log_event("backend started", env=settings.app_env, recovered=recovered)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TriageZero API",
        version="0.1.0",
        description=(
            "TriageZero investigation API with deterministic analysis by default "
            "and optional Gemini/Google ADK providers. Pub/Sub, Firestore, and "
            "Cloud Storage remain future adapters."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["authorization", "content-type", "idempotency-key"],
        max_age=600,
    )

    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        # Fast-fail on a declared oversized body. This is only the cheap first
        # gate: a chunked request carries no Content-Length, so the ingest
        # route also enforces the cap on bytes actually received.
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > get_settings().max_request_bytes
        ):
            return JSONResponse(
                status_code=413,
                content=error_body(
                    "request_too_large",
                    f"Request exceeds the configured maximum of "
                    f"{get_settings().max_request_bytes} bytes.",
                ),
            )
        return await call_next(request)

    register_error_handlers(app)
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(investigations.router, prefix="/api/v1", tags=["investigations"])

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"service": "triagezero-api", "docs": "/docs", "health": "/api/v1/health"}

    return app


app = create_app()
