from redis.asyncio import Redis

from .config import get_settings


redis_client: Redis = Redis.from_url(get_settings().redis_url, decode_responses=True)


async def check_redis() -> bool:
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False


async def close_redis() -> None:
    await redis_client.aclose()
