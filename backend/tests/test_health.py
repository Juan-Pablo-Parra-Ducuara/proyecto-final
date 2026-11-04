import httpx

from app.main import app


async def _get_health() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/health")


async def test_health_ok():
    response = await _get_health()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"postgres": "ok", "redis": "ok"},
    }


async def test_health_503_si_falla_postgres(monkeypatch):
    async def falso_fallo() -> bool:
        return False

    monkeypatch.setattr("app.main.check_database", falso_fallo)

    response = await _get_health()

    assert response.status_code == 503
    assert response.json()["checks"]["postgres"] == "error"
    assert response.json()["checks"]["redis"] == "ok"


async def test_health_503_si_falla_redis(monkeypatch):
    async def falso_fallo() -> bool:
        return False

    monkeypatch.setattr("app.main.check_redis", falso_fallo)

    response = await _get_health()

    assert response.status_code == 503
    assert response.json()["checks"]["postgres"] == "ok"
    assert response.json()["checks"]["redis"] == "error"
