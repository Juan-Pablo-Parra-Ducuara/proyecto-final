import urllib.error

import pytest

import client


class CabecerasFalsas(dict):
    """Doble de las cabeceras HTTP devueltas por request_json."""


def test_login_guarda_la_cookie_del_dashboard(monkeypatch):
    cabeceras = CabecerasFalsas(
        {
            "Set-Cookie": (
                "clicker_session=token-firmado; HttpOnly; Path=/"
            )
        }
    )

    monkeypatch.setattr(
        client,
        "request_json",
        lambda *args, **kwargs: ({"ok": True}, cabeceras),
    )

    cliente = client.LocalSocketClient(password="clave")

    cliente.login()

    assert cliente.cookie == "token-firmado"
    assert cliente.password is None


def test_crear_ticket_de_escritorio(monkeypatch):
    visto = {}

    def falso(url, **kwargs):
        visto["url"] = url
        visto.update(kwargs)
        return {"ticket": "ticket-123"}, {}

    monkeypatch.setattr(client, "request_json", falso)

    cliente = client.LocalSocketClient()
    cliente.cookie = "token-firmado"

    assert cliente.create_desktop_ticket() == "ticket-123"
    assert visto["url"].endswith("/auth/desktop-ticket")
    assert visto["headers"]["Cookie"] == "clicker_session=token-firmado"


def test_login_rechaza_contraseña_incorrecta(monkeypatch):
    error = urllib.error.HTTPError(
        "http://localhost/auth/login",
        401,
        "Unauthorized",
        {},
        None,
    )

    def fallar(*args, **kwargs):
        raise error

    monkeypatch.setattr(client, "request_json", fallar)

    cliente = client.LocalSocketClient(password="mala")

    with pytest.raises(RuntimeError, match="Contraseña incorrecta"):
        cliente.login()


def test_login_sin_contraseña(monkeypatch):
    def no_llamar(*args, **kwargs):
        raise AssertionError("No debía hacer la petición")

    monkeypatch.setattr(client, "request_json", no_llamar)

    cliente = client.LocalSocketClient()

    with pytest.raises(RuntimeError, match="Falta la contraseña"):
        cliente.login()
