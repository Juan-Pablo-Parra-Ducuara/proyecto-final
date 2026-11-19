async def test_login_password_incorrecta(client):
    response = await client.post("/auth/login", json={"password": "incorrecta"})

    assert response.status_code == 401


async def test_login_y_me(client):
    response = await client.post(
        "/auth/login", json={"password": "test-password"}
    )

    assert response.status_code == 200
    assert response.cookies.get("clicker_session")

    response = await client.get("/auth/me")
    assert response.status_code == 200
    assert response.json() == {"role": "dashboard"}


async def test_logout(client):
    await client.post("/auth/login", json={"password": "test-password"})

    response = await client.post("/auth/logout")
    assert response.status_code == 200

    response = await client.get("/auth/me")
    assert response.status_code == 401


async def test_endpoint_protegido_sin_login(client):
    response = await client.get("/students")

    assert response.status_code == 401


async def test_ticket_de_escritorio_loguea_al_navegador(
    dashboard_client, navegador_client
):
    response = await dashboard_client.post("/auth/desktop-ticket")
    assert response.status_code == 200

    ticket = response.json()["ticket"]

    response = await navegador_client.post(
        "/auth/desktop-login", json={"ticket": ticket}
    )

    assert response.status_code == 200
    assert navegador_client.cookies.get("clicker_session")

    response = await navegador_client.get("/auth/me")
    assert response.status_code == 200


async def test_ticket_de_escritorio_es_de_un_solo_uso(
    dashboard_client, navegador_client
):
    ticket = (await dashboard_client.post("/auth/desktop-ticket")).json()[
        "ticket"
    ]

    primera = await navegador_client.post(
        "/auth/desktop-login", json={"ticket": ticket}
    )
    assert primera.status_code == 200

    navegador_client.cookies.clear()

    segunda = await navegador_client.post(
        "/auth/desktop-login", json={"ticket": ticket}
    )
    assert segunda.status_code == 401


async def test_ticket_de_escritorio_invalido(navegador_client):
    response = await navegador_client.post(
        "/auth/desktop-login", json={"ticket": "ticket-falso"}
    )

    assert response.status_code == 401
