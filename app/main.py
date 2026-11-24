from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import auth_pages, chat, dev, documents, health, kb, pages, research, video

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI 学习知识工作台",
        description="可溯源的知识库 + 多模式 AI 工作台",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.exception_handler(HTTPException)
    async def http_exc_handler(_request: Request, exc: HTTPException):
        if (
            300 <= exc.status_code < 400
            and exc.headers
            and any(k.lower() == "location" for k in exc.headers)
        ):
            location = next(
                v for k, v in exc.headers.items() if k.lower() == "location"
            )
            return RedirectResponse(url=location, status_code=exc.status_code)
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": str(exc.errors())}},
        )

    settings = get_settings()
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    # Session 须在 CORS 之外更靠近应用（后添加的中间件更早执行）
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="awb_session",
        same_site="lax",
        https_only=False,
        max_age=60 * 60 * 24 * 14,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth_pages.router)
    app.include_router(kb.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(video.router)
    app.include_router(research.router)
    app.include_router(dev.router)
    app.include_router(pages.router)
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    return app


app = create_app()
