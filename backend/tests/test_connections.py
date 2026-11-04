from app.db import check_database
from app.redis_client import check_redis


async def test_postgres_conectado():
    assert await check_database() is True


async def test_redis_conectado():
    assert await check_redis() is True
