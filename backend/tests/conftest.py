import os

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://clicker:clicker@localhost:5432/clicker_test"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["API_KEY"] = "test-api-key"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DASHBOARD_PASSWORD"] = "test-password"

import pytest_asyncio

from app.db import dispose_engine, init_models
from app.redis_client import redis_client


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def prepare_databases():
    await init_models()
    await redis_client.flushdb()
    yield
    await redis_client.flushdb()
    await redis_client.aclose()
    await dispose_engine()
