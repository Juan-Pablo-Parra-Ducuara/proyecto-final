from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    from . import models  # noqa: F401  (registra las tablas en el metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_database() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    await engine.dispose()


if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        await init_models()
        await dispose_engine()
        print("Tablas creadas en PostgreSQL.")

    asyncio.run(main())
