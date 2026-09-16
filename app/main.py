import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import api_router
from app.config.settings import ensure_production_safety, get_settings
from app.database.db import init_db
from app.rate_limit import limiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    settings = get_settings()
    if not settings.google_api_key:
        logger.warning(
            "GOOGLE_API_KEY is not set. Set it in your .env file before calling /chat or /upload."
        )

    # Refuses to start in production with an insecure/incomplete config
    # (missing JWT secret, wide-open CORS). In development it just warns.
    ensure_production_safety(settings)

    # Create the `users` table (chat-history tables are created lazily by
    # SQLChatMessageHistory the first time each user sends a message).
    logger.info("Initializing database...")
    init_db()

    # Note: unlike a single-tenant demo, the vector store is no longer
    # built here at startup - each authenticated user's store is built
    # (or loaded from disk) exactly once, the first time THAT user hits
    # /upload or /chat. See app/services/vectorstore_service.py.
    logger.info("Startup complete.")

    yield
    # --- Shutdown --- (nothing to clean up currently)


def create_app() -> FastAPI:
    app = FastAPI(
        title="DocPilot",
        description=(
            "![DocPilot](/static/logo.png)\n\n"
            "A multi-tenant Retrieval-Augmented Generation API built with LangChain and "
            "FastAPI. Register/log in, then upload PDF/DOCX/TXT documents and chat with "
            "them, with per-user conversation memory and source citations."
        ),
        version="3.0.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    settings = get_settings()
    allowed_origins = (
        ["*"]
        if settings.frontend_url == "*"
        else [origin.strip() for origin in settings.frontend_url.split(",") if origin.strip()]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allowed_origins != ["*"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Serves the DocPilot logo (and anything else dropped in app/static/)
    # at /static/<filename> - e.g. /static/logo.png.
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(api_router)

    @app.get("/", tags=["Health"])
    async def root():
        return {"status": "ok", "service": "DocPilot"}

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        from fastapi.responses import FileResponse

        return FileResponse(str(STATIC_DIR / "logo.png"))

    return app


app = create_app()
