import asyncio

import pytest
import socketio

from app.redis_client import redis_client

PREGUNTA = {
    "text": "¿Cuánto es 3 + 4?",
    "option_a": "6",
    "option_b": "7",
    "option_c": "8",
    "option_d": "9",
    "correct_option": "B",
}


async def _crear_pregunta(client) -> dict:
    response = await client.post("/questions", json=PREGUNTA)
    assert response.status_code == 201
    return response.json()


async def _crear_estudiante(client, aruco_id: int = 1, name: str = "Ana") -> None:
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


async def _cookie_dashboard(client) -> str:
    response = await client.post(
        "/auth/login", json={"password": "test-password"}
    )
    cookie = response.cookies.get("clicker_session")
    assert cookie
    return cookie


async def _conectar_local(url: str) -> socketio.AsyncClient:
    client = socketio.AsyncClient(reconnection=False)
    await client.connect(
        url,
        auth={"role": "local", "api_key": "test-api-key"},
        transports=["websocket"],
    )
    return client


async def _conectar_dashboard(url: str, cookie: str) -> socketio.AsyncClient:
    client = socketio.AsyncClient(reconnection=False)
    await client.connect(
        url,
        headers={"Cookie": f"clicker_session={cookie}"},
        transports=["websocket"],
    )
    return client


async def _esperar(lista: list, cantidad: int = 1, timeout: float = 3.0) -> list:
    loop = asyncio.get_running_loop()
    limite = loop.time() + timeout
    while loop.time() < limite:
        if len(lista) >= cantidad:
            return lista
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"No llegaron {cantidad} evento(s); recibidos: {len(lista)}"
    )


async def test_conexion_local_con_api_key_invalida(live_server):
    client = socketio.AsyncClient(reconnection=False)

    with pytest.raises(socketio.exceptions.ConnectionError):
        await client.connect(
            live_server,
            auth={"role": "local", "api_key": "incorrecta"},
            transports=["websocket"],
        )

    assert not client.connected


async def test_dashboard_sin_cookie_rechazado(live_server):
    client = socketio.AsyncClient(reconnection=False)

    with pytest.raises(socketio.exceptions.ConnectionError):
        await client.connect(live_server, transports=["websocket"])


async def test_state_sync_al_conectar(dashboard_client, live_server):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    estados = []
    client = socketio.AsyncClient(reconnection=False)

    @client.on("state:sync")
    async def _on_state(data):
        estados.append(data)

    await client.connect(
        live_server,
        auth={"role": "local", "api_key": "test-api-key"},
        transports=["websocket"],
    )

    try:
        estado = (await _esperar(estados))[0]
        assert estado["session_id"] == session_id
        assert estado["status"] == "open"
        assert estado["roster"] == [1]
        assert estado["counts"] == {"A": 0, "B": 0, "C": 0, "D": 0}
    finally:
        await client.disconnect()


async def test_voto_valido_emite_tally(dashboard_client, live_server):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    cookie = await _cookie_dashboard(dashboard_client)
    dashboard = await _conectar_dashboard(live_server, cookie)
    local = await _conectar_local(live_server)

    tallies = []

    @dashboard.on("tally:update")
    async def _on_tally(data):
        tallies.append(data)

    try:
        await local.emit(
            "vote:cast",
            {"session_id": session_id, "aruco_id": 1, "option": "A"},
        )
        tally = (await _esperar(tallies))[0]

        assert tally["counts"] == {"A": 1, "B": 0, "C": 0, "D": 0}
        assert tally["total"] == 1
        assert tally["voted"] == [1]
        assert tally["missing"] == []
        assert await redis_client.hget(
            f"session:{session_id}:votes", "1"
        ) == "A"
    finally:
        await local.disconnect()
        await dashboard.disconnect()


async def test_voto_desconocido_rechazado(dashboard_client, live_server):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])
    local = await _conectar_local(live_server)
    rechazos = []

    @local.on("vote:rejected")
    async def _on_rejected(data):
        rechazos.append(data)

    try:
        await local.emit(
            "vote:cast",
            {"session_id": session_id, "aruco_id": 999, "option": "A"},
        )
        rechazo = (await _esperar(rechazos))[0]
        assert rechazo == {"aruco_id": 999, "reason": "unknown"}
    finally:
        await local.disconnect()


async def test_voto_invalido_rechazado(dashboard_client, live_server):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])
    local = await _conectar_local(live_server)
    rechazos = []

    @local.on("vote:rejected")
    async def _on_rejected(data):
        rechazos.append(data)

    try:
        await local.emit(
            "vote:cast",
            {"session_id": session_id, "aruco_id": 1, "option": "Z"},
        )
        rechazo = (await _esperar(rechazos))[0]
        assert rechazo == {"aruco_id": 1, "reason": "invalid"}
    finally:
        await local.disconnect()


async def test_voto_con_sesion_cerrada_rechazado(dashboard_client, live_server):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])
    await dashboard_client.post(f"/sessions/{session_id}/close")

    local = await _conectar_local(live_server)
    rechazos = []

    @local.on("vote:rejected")
    async def _on_rejected(data):
        rechazos.append(data)

    try:
        await local.emit(
            "vote:cast",
            {"session_id": session_id, "aruco_id": 1, "option": "A"},
        )
        rechazo = (await _esperar(rechazos))[0]
        assert rechazo == {"aruco_id": 1, "reason": "closed"}
    finally:
        await local.disconnect()


async def test_voto_con_sesion_vieja_rechazado(dashboard_client, live_server):
    pregunta_vieja = await _crear_pregunta(dashboard_client)
    pregunta_nueva = await _crear_pregunta(dashboard_client)
    await _crear_estudiante(dashboard_client)
    session_vieja = await _abrir_sesion(dashboard_client, pregunta_vieja["id"])
    await dashboard_client.post(f"/sessions/{session_vieja}/close")
    session_nueva = await _abrir_sesion(dashboard_client, pregunta_nueva["id"])

    local = await _conectar_local(live_server)
    rechazos = []

    @local.on("vote:rejected")
    async def _on_rejected(data):
        rechazos.append(data)

    try:
        await local.emit(
            "vote:cast",
            {"session_id": session_vieja, "aruco_id": 1, "option": "A"},
        )
        rechazo = (await _esperar(rechazos))[0]
        assert rechazo == {"aruco_id": 1, "reason": "stale_session"}
        assert session_nueva != session_vieja
    finally:
        await local.disconnect()


async def test_voto_duplicado_sobrescribe(dashboard_client, live_server):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    cookie = await _cookie_dashboard(dashboard_client)
    dashboard = await _conectar_dashboard(live_server, cookie)
    local = await _conectar_local(live_server)
    tallies = []

    @dashboard.on("tally:update")
    async def _on_tally(data):
        tallies.append(data)

    try:
        await local.emit(
            "vote:cast",
            {"session_id": session_id, "aruco_id": 1, "option": "A"},
        )
        await _esperar(tallies, cantidad=1)

        await local.emit(
            "vote:cast",
            {"session_id": session_id, "aruco_id": 1, "option": "C"},
        )
        await _esperar(tallies, cantidad=2)

        assert tallies[-1]["counts"] == {"A": 0, "B": 0, "C": 1, "D": 0}
        assert tallies[-1]["total"] == 1
    finally:
        await local.disconnect()
        await dashboard.disconnect()


# ============================================================
# Socket del estudiante: solo lectura y sin datos del curso.
# ============================================================

CUENTA = {
    "name": "Ana",
    "email": "ana@example.com",
    "password": "secreta123",
}


async def _crear_cuenta_estudiante(client, datos=None) -> dict:
    datos = datos or CUENTA
    response = await client.post("/students/accounts", json=datos)
    assert response.status_code == 201
    return response.json()


async def _cookie_estudiante(client, datos=None) -> str:
    datos = datos or CUENTA
    response = await client.post(
        "/student-auth/login",
        json={"email": datos["email"], "password": datos["password"]},
    )
    assert response.status_code == 200
    return response.cookies.get("clicker_student_session")


async def _conectar_estudiante(live_server, cookie: str):
    client = socketio.AsyncClient(reconnection=False)
    await client.connect(
        live_server,
        headers={"Cookie": f"clicker_student_session={cookie}"},
        transports=["websocket"],
    )
    return client


async def test_socket_estudiante_recibe_estado_saneado(
    dashboard_client, live_server
):
    pregunta = await _crear_pregunta(dashboard_client)
    await _crear_cuenta_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    cookie = await _cookie_estudiante(dashboard_client)
    estados = []
    client = socketio.AsyncClient(reconnection=False)

    @client.on("state:sync")
    async def _on_state(data):
        estados.append(data)

    await client.connect(
        live_server,
        headers={"Cookie": f"clicker_student_session={cookie}"},
        transports=["websocket"],
    )

    try:
        estado = (await _esperar(estados))[0]

        assert estado["session_id"] == session_id
        assert estado["status"] == "open"
        assert estado["question"] == {
            "id": pregunta["id"],
            "text": pregunta["text"],
        }
        assert "roster" not in estado
        assert "counts" not in estado
        assert "your_vote" in estado
    finally:
        await client.disconnect()


async def test_socket_estudiante_recibe_apertura_sin_roster(
    dashboard_client, live_server
):
    await _crear_cuenta_estudiante(dashboard_client)

    cookie = await _cookie_estudiante(dashboard_client)
    aperturas = []
    client = await _conectar_estudiante(live_server, cookie)

    @client.on("vote:open")
    async def _on_open(data):
        aperturas.append(data)

    try:
        pregunta = await _crear_pregunta(dashboard_client)
        session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

        evento = (await _esperar(aperturas))[0]

        assert evento["session_id"] == session_id
        assert evento["status"] == "open"
        assert evento["question"] == {
            "id": pregunta["id"],
            "text": pregunta["text"],
        }
        assert "roster" not in evento
        assert "correct_option" not in evento["question"]
        assert set(evento["options"]) == {"A", "B", "C", "D"}
    finally:
        await client.disconnect()


async def test_socket_estudiante_recibe_su_resultado(
    dashboard_client, live_server
):
    pregunta = await _crear_pregunta(dashboard_client)
    cuenta = await _crear_cuenta_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    cookie = await _cookie_estudiante(dashboard_client)
    finales = []
    aceptados = []
    client = await _conectar_estudiante(live_server, cookie)

    @client.on("results:final")
    async def _on_final(data):
        finales.append(data)

    @client.on("vote:accepted")
    async def _on_accepted(data):
        aceptados.append(data)

    local = await _conectar_local(live_server)

    try:
        await local.emit(
            "vote:cast",
            {"session_id": session_id, "aruco_id": cuenta["id"], "option": "B"},
        )

        # Esperar a que el voto llegue antes de cerrar.
        await asyncio.sleep(0.2)

        acuse = (await _esperar(aceptados))[0]
        assert acuse == {
            "session_id": session_id,
            "student_id": cuenta["id"],
            "option": "B",
        }

        await dashboard_client.post(f"/sessions/{session_id}/close")

        evento = (await _esperar(finales))[0]

        assert "per_student" not in evento
        assert evento["correct_option"] == "B"
        assert evento["counts"] == {"A": 0, "B": 1, "C": 0, "D": 0}
        assert evento["your"] == {"option": "B", "correct": True}
    finally:
        await local.disconnect()
        await client.disconnect()


async def test_socket_estudiante_no_puede_votar(dashboard_client, live_server):
    pregunta = await _crear_pregunta(dashboard_client)
    cuenta = await _crear_cuenta_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    cookie = await _cookie_estudiante(dashboard_client)
    aceptados = []
    rechazos = []
    client = await _conectar_estudiante(live_server, cookie)

    @client.on("vote:accepted")
    async def _on_accepted(data):
        aceptados.append(data)

    @client.on("vote:rejected")
    async def _on_rejected(data):
        rechazos.append(data)

    try:
        await client.emit(
            "vote:cast",
            {"session_id": session_id, "aruco_id": cuenta["id"], "option": "A"},
        )

        await asyncio.sleep(0.3)

        assert aceptados == []
        assert rechazos == []
        assert await redis_client.hget(
            f"session:{session_id}:votes", str(cuenta["id"])
        ) is None
    finally:
        await client.disconnect()


async def test_dashboard_escanea_qr_token(dashboard_client, live_server):
    """El dashboard (escáner del teléfono) puede enviar votos con qr_token."""

    pregunta = await _crear_pregunta(dashboard_client)
    cuenta = await _crear_cuenta_estudiante(dashboard_client)
    session_id = await _abrir_sesion(dashboard_client, pregunta["id"])

    # Obtener el token permanente desde el panel del estudiante.
    await _cookie_estudiante(dashboard_client)
    panel = await dashboard_client.get("/student-auth/panel")
    assert panel.status_code == 200
    qr_token = panel.json()["qr_token"]
    assert qr_token

    cookie = await _cookie_dashboard(dashboard_client)
    escaner = await _conectar_dashboard(live_server, cookie)

    tallies = []
    aceptados = []

    @escaner.on("tally:update")
    async def _on_tally(data):
        tallies.append(data)

    @escaner.on("vote:accepted")
    async def _on_accepted(data):
        aceptados.append(data)

    try:
        await escaner.emit(
            "vote:cast",
            {"session_id": session_id, "qr_token": qr_token, "option": "D"},
        )

        tally = (await _esperar(tallies))[0]
        acuse = (await _esperar(aceptados))[0]

        assert tally["counts"] == {"A": 0, "B": 0, "C": 0, "D": 1}
        assert tally["voted"] == [cuenta["id"]]
        assert acuse["student_id"] == cuenta["id"]
        assert acuse["option"] == "D"
    finally:
        await escaner.disconnect()
