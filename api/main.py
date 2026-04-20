"""FastAPI 入口。"""

from __future__ import annotations

import logging
import sys
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nacos_skill_client.config import Config
from nacos_skill_client.exceptions import NacosAPIError, NacosAuthError, NacosNotFoundError

from .routes import router as skills_router

logger = logging.getLogger(__name__)

config = Config.load()
config.setup_logging()

app = FastAPI(
    title="Nacos Skill Client API",
    description="Nacos Skill Registry — Skill 管理与自动路由 API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(skills_router)


@app.exception_handler(NacosNotFoundError)
async def not_found_handler(request: Request, exc: NacosNotFoundError) -> JSONResponse:
    logger.warning("404 - %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc), "code": exc.code if exc.code else None},
    )


@app.exception_handler(NacosAuthError)
async def auth_handler(request: Request, exc: NacosAuthError) -> JSONResponse:
    logger.warning("401 - %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=401,
        content={"detail": str(exc), "code": exc.code if exc.code else None},
    )


@app.exception_handler(NacosAPIError)
async def api_error_handler(request: Request, exc: NacosAPIError) -> JSONResponse:
    logger.error("500 - %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "code": exc.code if exc.code else None},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("422 - %s %s: validation error", request.method, request.url.path)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("500 - %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """请求日志中间件：记录每个请求的方法、路径、耗时、状态码。"""
    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)
    logger.info("%s %s → %d (%dms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "version": "0.2.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.api.reload,
        log_level=config.api.log_level,
    )
