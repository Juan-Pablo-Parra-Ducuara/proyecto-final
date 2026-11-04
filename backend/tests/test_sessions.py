from sqlalchemy import select

from app import services
from app.db import SessionLocal
from app.models import Vote
from app.redis_client import redis_client

PREGUNTA = {
    "text": "¿Cuál es la capital de Francia?",
    "option_a": "Madrid",
    "option_b": "Roma",
    "option_c": "París",
    "option_d": "Berlín",
    "correct_option": "C",
}


async def _crear_pregunta(client) -> dict:
    response = await client.post("/questions", json=PREGUNTA)
    assert response.status_code == 201
    return response.json()


async def _crear_estudiantes(client) -> None:
    for aruco_id, name in ((1, "Ana"), (2, "Beto")):
        response = await client.post(
            "/students", json={"name": name, "aruco_id": aruco_id}
        )
        assert response.status_code == 201


async def _abrir_sesion(client, question_id: int) -> int:
    response = await client.post(
        "/sessions", json={"question_id": question_id}
    )
    assert response.status_code == 201
    return response.json()["session_id"]


async def test_abrir_sesion_carga_redis(dashboard_client):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiantes(dashboard_client)

    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    assert await redis_client.get("active_session") == str(session_id)
    assert await redis_client.smembers(
        f"session:{session_id}:roster"
    ) == {"1", "2"}


async def test_no_permite_dos_sesiones_abiertas(dashboard_client):
    pregunta = await _crear_pregunta(dashboard_client)
    await _abrir_sesion(dashboard_client, pregunta["id"])

    response = await dashboard_client.post(
        "/sessions", json={"question_id": pregunta["id"]}
    )

    assert response.status_code == 409


async def test_cerrar_persiste_ultimo_voto(dashboard_client):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiantes(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    await services.cast_vote(session_id, 1, "A")
    await services.cast_vote(session_id, 1, "C")
    await services.cast_vote(session_id, 2, "A")

    response = await dashboard_client.post(f"/sessions/{session_id}/close")

    assert response.status_code == 200
    data = response.json()
    assert data["counts"] == {"A": 1, "B": 0, "C": 1, "D": 0}
    assert data["correct_option"] == "C"

    por_nombre = {p["name"]: p for p in data["per_student"]}
    assert por_nombre["Ana"]["option"] == "C"
    assert por_nombre["Ana"]["correct"] is True
    assert por_nombre["Beto"]["option"] == "A"
    assert por_nombre["Beto"]["correct"] is False

    assert await redis_client.get("active_session") is None
    assert not await redis_client.exists(f"session:{session_id}:votes")


async def test_cierre_idempotente(dashboard_client):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiantes(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])
    await services.cast_vote(session_id, 1, "C")

    primera = await dashboard_client.post(f"/sessions/{session_id}/close")
    segunda = await dashboard_client.post(f"/sessions/{session_id}/close")

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert primera.json() == segunda.json()

    async with SessionLocal() as db:
        votos = (
            await db.execute(
                select(Vote).where(Vote.session_id == session_id)
            )
        ).scalars().all()
    assert len(votos) == 1


async def test_sesion_activa_y_resultados(dashboard_client):
    estado = (await dashboard_client.get("/sessions/active")).json()
    assert estado == {"session_id": None, "status": "closed"}

    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiantes(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])
    await services.cast_vote(session_id, 1, "B")

    estado = (await dashboard_client.get("/sessions/active")).json()
    assert estado["session_id"] == session_id
    assert estado["status"] == "open"
    assert estado["roster"] == [1, 2]
    assert estado["counts"] == {"A": 0, "B": 1, "C": 0, "D": 0}
    assert estado["voted"] == [1]
    assert estado["missing"] == [2]

    await dashboard_client.post(f"/sessions/{session_id}/close")
    estado = (await dashboard_client.get("/sessions/active")).json()
    assert estado == {"session_id": None, "status": "closed"}

    resultados = (
        await dashboard_client.get(f"/sessions/{session_id}/results")
    ).json()
    assert resultados["counts"] == {"A": 0, "B": 1, "C": 0, "D": 0}


async def test_cerrar_sesion_inexistente(dashboard_client):
    response = await dashboard_client.post("/sessions/999/close")

    assert response.status_code == 404
