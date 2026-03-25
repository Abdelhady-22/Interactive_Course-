"""FastAPI application entry point with production-grade logging, health checks, and error handling."""
import logging
import logging.handlers
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import courses, paragraphs, assets, agent
from app.config import settings
from app.middleware import register_error_handlers


# --- Logging Setup ---

def setup_logging():
    """Configure logging with console + rotating file handler."""
    # Create logs directory
    log_dir = Path(settings.log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Format
    fmt = logging.Formatter(
        "%(asctime)s | %(name)-35s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root_logger.addHandler(console)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        settings.log_file,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root_logger.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.info(f"Logging configured: level={settings.log_level}, file={settings.log_file}")


setup_logging()

logger = logging.getLogger(__name__)


# --- FastAPI App ---

app = FastAPI(
    title=settings.app_name,
    description=(
        "AI-powered layout director for interactive educational courses. "
        "Upload a video + script → AI agent decides optimal screen layouts → "
        "Review and approve → Publish for learners."
    ),
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — configurable origins
_origins = [o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register structured error handlers
register_error_handlers(app)

# Register routers
app.include_router(courses.router)
app.include_router(paragraphs.router)
app.include_router(assets.router)
app.include_router(agent.router)


# --- Health & Info ---

@app.get("/", tags=["Health"])
def root():
    """API info."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    """Basic health check."""
    return {"status": "ok"}


@app.get("/health/detailed", tags=["Health"])
def health_detailed():
    """Detailed health check — tests database and LLM connectivity.

    Returns:
        status: "healthy" | "degraded" | "unhealthy"
        db: "ok" | "error: ..."
        llm: "ok" | "error: ..."
    """
    result = {"status": "healthy", "db": "unknown", "llm": "unknown"}
    is_degraded = False

    # Check database
    db = None
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        result["db"] = "ok"
    except Exception as e:
        result["db"] = f"error: {str(e)[:100]}"
        is_degraded = True
        logger.warning(f"Health check: DB connectivity failed: {e}")
    finally:
        if db:
            db.close()

    # Check LLM availability
    try:
        import httpx
        llm_base = settings.llm_api_base
        if llm_base:
            # Ollama-style health check
            resp = httpx.get(f"{llm_base}/api/tags", timeout=5.0)
            if resp.status_code == 200:
                result["llm"] = "ok"
            else:
                result["llm"] = f"error: HTTP {resp.status_code}"
                is_degraded = True
        else:
            result["llm"] = "ok (cloud provider — no local health check)"
    except Exception as e:
        result["llm"] = f"error: {str(e)[:100]}"
        is_degraded = True
        logger.warning(f"Health check: LLM connectivity failed: {e}")

    if is_degraded:
        result["status"] = "degraded"

    return result


logger.info(f"App started: {settings.app_name} v{settings.app_version}")
