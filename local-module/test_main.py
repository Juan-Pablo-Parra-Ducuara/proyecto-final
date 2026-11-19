import main


class ClienteFalso:
    server_url = "http://127.0.0.1:8000/"

    def create_desktop_ticket(self):
        return "ticket/con-barra"


def test_abrir_dashboard_usa_el_ticket(monkeypatch):
    abierto = {}

    monkeypatch.setattr(
        main.webbrowser,
        "open",
        lambda url: abierto.setdefault("url", url),
    )

    main.abrir_dashboard(ClienteFalso())

    assert abierto["url"] == (
        "http://127.0.0.1:8000/?desktop_ticket=ticket%2Fcon-barra"
    )
