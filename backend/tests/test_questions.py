PREGUNTA = {
    "text": "¿Cuánto es 2 + 2?",
    "option_a": "3",
    "option_b": "4",
    "option_c": "5",
    "option_d": "6",
    "correct_option": "B",
}


async def test_crear_y_listar_preguntas(dashboard_client):
    response = await dashboard_client.post("/questions", json=PREGUNTA)

    assert response.status_code == 201
    assert response.json()["correct_option"] == "B"

    response = await dashboard_client.get("/questions")
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_opcion_correcta_invalida(dashboard_client):
    payload = {**PREGUNTA, "correct_option": "E"}

    response = await dashboard_client.post("/questions", json=payload)

    assert response.status_code == 422


async def test_pregunta_inexistente_al_abrir_sesion(dashboard_client):
    response = await dashboard_client.post(
        "/sessions", json={"question_id": 999}
    )

    assert response.status_code == 404
