"""FastAPI application entrypoint (Phase 1: health, dashboard badges, evals)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.integrations.supabase.client import check_supabase_connectivity

logger = get_logger(__name__)

_SKIP_SUPABASE_STARTUP = os.getenv("PHASE1_SKIP_SUPABASE_STARTUP_CHECK", "").lower() in (
    "1",
    "true",
    "yes",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    settings = get_settings()
    if _SKIP_SUPABASE_STARTUP:
        logger.warning(
            "startup_supabase_check_skipped",
            extra={"correlation_id": "-"},
        )
    else:
        ok, msg = await check_supabase_connectivity(settings)
        if not ok:
            raise RuntimeError(
                f"Supabase connectivity check failed at startup ({msg}). "
                "Verify SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or set "
                "PHASE1_SKIP_SUPABASE_STARTUP_CHECK=true for local offline work.",
            )
        logger.info("startup_supabase_ok", extra={"correlation_id": "-"})

    # Phase 4: load RAG index from disk (safe if absent; chat degrades to Phase 3 skeleton).
    from app.rag.retrieve import load_rag_index_from_default

    await load_rag_index_from_default()

    # Phase 4 extended: load MF metrics store from disk (safe if absent; degrades to RAG-only).
    from app.rag.metrics_store import load_metrics_store_from_default

    await load_metrics_store_from_default()
    logger.info("mf_metrics_store_startup_complete", extra={"correlation_id": "-"})

    # Guardrail 6: startup summary of active LLM guardrails.
    from app.llm.response_cache import log_guardrails_active

    log_guardrails_active(settings)

    yield


app = FastAPI(
    title="Groww Product Operations Ecosystem API",
    version="0.1.0",
    lifespan=lifespan,
)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.api.v1 import api_router


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = request.headers.get("x-correlation-id") or request.headers.get("X-Correlation-ID")
    if not cid:
        cid = str(uuid4())
    request.state.correlation_id = cid[:128]
    from app.core.context import correlation_id as _cid_var
    _cid_var.set(request.state.correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = request.state.correlation_id
    return response


def _setup_cors(application: FastAPI) -> None:
    settings = get_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_setup_cors(app)
app.include_router(api_router)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "groww-product-ops-api", "docs": "/docs"}
