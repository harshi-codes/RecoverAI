"""
RecoverAI – FastAPI application entry point.

Startup sequence:
1. Load settings
2. Load trained ML model into memory (fails fast if not trained yet)
3. Register all API routers
4. Expose /health endpoint
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.ml import model as ml_model_module

logger = logging.getLogger(__name__)
settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ── Lifespan: startup + shutdown ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    logger.info("RecoverAI backend starting up...")
    try:
        ml_model_module.load_model(settings.ml_artifacts_dir)
        logger.info("ML model loaded successfully.")
    except FileNotFoundError as e:
        logger.warning(f"ML model not loaded (prediction endpoints will fail): {e}")
    yield
    # SHUTDOWN
    logger.info("RecoverAI backend shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="RecoverAI API",
    description=(
        "Autonomous Revenue Recovery Intelligence Platform for merchants. "
        "Detects failed payments, scores recoverability via ML, selects recovery "
        "actions through a policy engine, and tracks actual recovered revenue."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────
from app.api.ml import router as ml_router  # noqa: E402
from app.api.recovery import router as recovery_router  # noqa: E402

app.include_router(ml_router)
app.include_router(recovery_router)


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    """
    Returns application health status.
    Checks: API alive, ML model loaded.
    """
    model_loaded = ml_model_module._model_instance is not None
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "ml_model_loaded": model_loaded,
        "ml_model_version": "1.0.0" if model_loaded else None,
    }


@app.get("/", include_in_schema=False)
async def root():
    return {"message": "RecoverAI API — see /docs for endpoints."}
