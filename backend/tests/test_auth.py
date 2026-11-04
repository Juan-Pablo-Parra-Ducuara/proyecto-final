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
