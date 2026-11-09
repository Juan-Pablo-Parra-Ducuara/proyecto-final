from contextlib import asynccontextmanager
from pathlib import Path

import socketio
from fastapi import FastAPI, Response, status
from fastapi.staticfiles import StaticFiles

from . import auth, routes
from .db import check_database, dispose_engine, init_models
from .redis_client import check_redis, close_redis
from .services import cleanup_stale_active_session
from .sockets import sio


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_models()
    await cleanup_stale_active_session()

    yield

    await close_redis()
    await dispose_engine()

api = FastAPI(title="Clicker por cámara", version="0.1.0", lifespan=lifespan)
api.include_router(auth.router)
api.include_router(routes.router)


@api.get("/health")
async def health(response: Response) -> dict:
    postgres_ok = await check_database()
    redis_ok = await check_redis()
    healthy = postgres_ok and redis_ok

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if healthy else "degraded",
        "checks": {
            "postgres": "ok" if postgres_ok else "error",
            "redis": "ok" if redis_ok else "error",
        },
    }


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    api.mount(
        "/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend"
    )


app = socketio.ASGIApp(sio, other_asgi_app=api)
