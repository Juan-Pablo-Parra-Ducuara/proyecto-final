import asyncio
import os
import socket as socket_module

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://clicker:clicker@localhost:5432/clicker_test"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["API_KEY"] = "test-api-key"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DASHBOARD_PASSWORD"] = "test-password"

import httpx
import pytest_asyncio
import socketio
import uvicorn
from sqlalchemy import text

from app.db import dispose_engine, engine, init_models
from app.main import app as asgi_app
from app.redis_client import redis_client


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def prepare_databases():
    await init_models()
    yield
    await redis_client.aclose()
    await dispose_engine()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def clean_state():
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE votes, voting_sessions, questions, students "
                "RESTART IDENTITY CASCADE"
            )
        )
    await redis_client.flushdb()
    yield


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client


@pytest_asyncio.fixture(loop_scope="session")
async def dashboard_client(client):
    response = await client.post(
        "/auth/login", json={"password": "test-password"}
    )
    assert response.status_code == 200
    return client


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def live_server(prepare_databases):
    with socket_module.socket(
        socket_module.AF_INET, socket_module.SOCK_STREAM
    ) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(
        asgi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())

    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.05)

    if not server.started:
        task.cancel()
        raise RuntimeError("uvicorn no arrancó para los tests de sockets")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    await task


@pytest_asyncio.fixture(loop_scope="session")
async def local_client(live_server):
    client = socketio.AsyncClient()
    await client.connect(
        live_server,
        auth={"role": "local", "api_key": "test-api-key"},
        transports=["websocket"],
    )
    yield client
    if client.connected:
        await client.disconnect()
