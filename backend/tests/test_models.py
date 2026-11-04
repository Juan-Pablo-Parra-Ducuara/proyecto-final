from sqlalchemy import text

from app.db import engine

TABLAS_ESPERADAS = {"students", "questions", "voting_sessions", "votes"}


async def test_tablas_creadas():
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tablas = {row[0] for row in result}

    assert TABLAS_ESPERADAS <= tablas
