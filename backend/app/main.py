"""FastAPI application entrypoint (Phase 1: health, dashboard badges, evals)."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.integrations.supabase.client import check_supabase_connectivity

logger = get_logger(__name__)


def _materialise_gcp_credentials() -> None:
    """Write GOOGLE_APPLICATION_CREDENTIALS_JSON to a temp file on cloud platforms.

    Railway (and other PaaS providers) cannot mount files, so the service-account
    JSON must be stored as a single env var. If that var is present and
    GOOGLE_APPLICATION_CREDENTIALS is not already pointing at a file, this
    function writes the JSON to a process-scoped temp file and sets the standard
    ADC env var so the google-cloud-* SDKs pick it up automatically.
    """
    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    if not creds_json:
        return
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    try:
        parsed = json.loads(creds_json)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="gcp_creds_"
        )
        json.dump(parsed, tmp)
        tmp.close()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
        logger.info(
            "gcp_credentials_materialised_from_env",
            extra={"correlation_id": "-", "path": tmp.name},
        )
    except Exception as exc:
        logger.warning(
            "gcp_credentials_materialise_failed",
            extra={"correlation_id": "-", "error": str(exc)[:120]},
        )


_materialise_gcp_credentials()

_SKIP_SUPABASE_STARTUP = os.getenv("PHASE1_SKIP_SUPABASE_STARTUP_CHECK", "").lower() in (
    "1",
    "true",
    "yes",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    settings = get_settings()
    if (settings.app_env or "").lower() == "development":
        from app.llm.response_cache import clear_cache

        clear_cache()
        logger.info("llm_response_cache_cleared_on_startup", extra={"correlation_id": "-"})
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
    from pathlib import Path

    from app.rag.retrieve import load_rag_index_from_default

    chunks_path = Path(__file__).resolve().parent / "rag" / "index" / "chunks.json"
    rag_mode = (settings.rag_storage_mode or "file").lower().strip()
    await load_rag_index_from_default()
    if rag_mode == "file" and not chunks_path.is_file():
        logger.warning(
            "RAG index (chunks.json) missing — run scripts/rebuild_index.py from the "
            "repository root to enable full RAG",
            extra={"correlation_id": "-", "path": str(chunks_path)},
        )

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
