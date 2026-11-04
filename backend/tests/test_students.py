async def test_crear_y_listar_estudiantes(dashboard_client):
    response = await dashboard_client.post(
        "/students", json={"name": "Ana", "aruco_id": 1}
    )

    assert response.status_code == 201
    assert response.json()["aruco_id"] == 1

    response = await dashboard_client.get("/students")
    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["Ana"]


async def test_aruco_duplicado_devuelve_409(dashboard_client):
    await dashboard_client.post(
        "/students", json={"name": "Ana", "aruco_id": 1}
    )

    response = await dashboard_client.post(
        "/students", json={"name": "Otra", "aruco_id": 1}
    )

    assert response.status_code == 409


async def test_carga_masiva_deduplica_por_aruco(dashboard_client):
    response = await dashboard_client.post(
        "/students/bulk",
        json=[
            {"name": "Ana", "aruco_id": 1},
            {"name": "Beto", "aruco_id": 2},
            {"name": "Ana actualizada", "aruco_id": 1},
        ],
    )

    assert response.status_code == 200
    assert response.json() == {"count": 2}

    response = await dashboard_client.get("/students")
    estudiantes = {s["aruco_id"]: s["name"] for s in response.json()}
    assert estudiantes == {1: "Ana actualizada", 2: "Beto"}
