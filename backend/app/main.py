from fastapi import FastAPI, Response, status

from .db import check_database
from .redis_client import check_redis

app = FastAPI(title="Clicker por cámara", version="0.1.0")


@app.get("/health")
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
