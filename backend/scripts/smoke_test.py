"""Prueba de humo sin cámara: siembra datos y simula votos por Socket.IO.

Requiere el backend levantado:
    uvicorn app.main:app --reload --port 8000

Uso (desde backend/):
    python scripts/smoke_test.py
    python scripts/smoke_test.py --keep-open --delay 1.5
    python scripts/smoke_test.py --server http://127.0.0.1:8000
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import socketio

from app.config import get_settings

ESTUDIANTES = [
    {"name": "Ana", "aruco_id": 1},
    {"name": "Beto", "aruco_id": 2},
    {"name": "Carla", "aruco_id": 3},
    {"name": "Diego", "aruco_id": 4},
]

PREGUNTA = {
    "text": "¿Cuál es la capital de Francia?",
    "option_a": "Madrid",
    "option_b": "Roma",
    "option_c": "París",
    "option_d": "Berlín",
    "correct_option": "C",
}

VOTOS_VALIDOS = [(1, "A"), (2, "B"), (3, "C"), (4, "A"), (1, "D")]
VOTOS_RECHAZADOS = [(999, "A"), (2, "Z")]


async def _esperar(lista: list, cantidad: int, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    limite = loop.time() + timeout
    while loop.time() < limite:
        if len(lista) >= cantidad:
            return
        await asyncio.sleep(0.02)
    raise RuntimeError(f"Se esperaban {cantidad} eventos y llegaron {len(lista)}")


async def main(server: str, keep_open: bool, delay: float) -> int:
    settings = get_settings()

    async with httpx.AsyncClient(base_url=server, timeout=10) as http:
        login = await http.post(
            "/auth/login", json={"password": settings.dashboard_password}
        )
        login.raise_for_status()
        cookie = login.cookies.get("clicker_session")

        estado = (await http.get("/sessions/active")).json()
        if estado.get("session_id"):
            print(f"Cerrando sesión previa #{estado['session_id']}...")
            await http.post(f"/sessions/{estado['session_id']}/close")

        await http.post("/students/bulk", json=ESTUDIANTES)
        pregunta = (await http.post("/questions", json=PREGUNTA)).json()
        sesion = (
            await http.post(
                "/sessions", json={"question_id": pregunta["id"]}
            )
        ).json()
        session_id = sesion["session_id"]
        print(f"Sesión #{session_id} abierta con {len(ESTUDIANTES)} alumnos.")

        local = socketio.AsyncClient(reconnection=False)
        dashboard = socketio.AsyncClient(reconnection=False)
        rechazos: list = []
        tallies: list = []

        @local.on("vote:rejected")
        async def _on_rejected(data):
            rechazos.append(data)

        @dashboard.on("tally:update")
        async def _on_tally(data):
            tallies.append(data)
            counts = data["counts"]
            print(
                f"  tally: A={counts['A']} B={counts['B']} "
                f"C={counts['C']} D={counts['D']} "
                f"total={data['total']} faltan={len(data['missing'])}"
            )

        await dashboard.connect(
            server,
            headers={"Cookie": f"clicker_session={cookie}"},
            transports=["websocket"],
        )
        await local.connect(
            server,
            auth={"role": "local", "api_key": settings.api_key},
            transports=["websocket"],
        )

        try:
            for aruco_id, option in VOTOS_VALIDOS:
                print(f"  voto: alumno {aruco_id} -> {option}")
                await local.emit(
                    "vote:cast",
                    {
                        "session_id": session_id,
                        "aruco_id": aruco_id,
                        "option": option,
                    },
                )
                await asyncio.sleep(delay)

            for aruco_id, option in VOTOS_RECHAZADOS:
                print(f"  intento inválido: alumno {aruco_id} -> {option}")
                await local.emit(
                    "vote:cast",
                    {
                        "session_id": session_id,
                        "aruco_id": aruco_id,
                        "option": option,
                    },
                )
                await asyncio.sleep(delay)

            await _esperar(tallies, len(VOTOS_VALIDOS))
            await _esperar(rechazos, len(VOTOS_RECHAZADOS))
        finally:
            await local.disconnect()
            await dashboard.disconnect()

        print("Rechazos recibidos:")
        for rechazo in rechazos:
            print(f"  aruco={rechazo['aruco_id']} motivo={rechazo['reason']}")

        if keep_open:
            print(
                f"\nSesión #{session_id} sigue abierta. "
                f"Abre {server} y ciérrala desde el dashboard."
            )
            return 0

        resultados = (
            await http.post(f"/sessions/{session_id}/close")
        ).json()
        print("\nResultados finales:")
        print(json.dumps(resultados, indent=2, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke test del clicker")
    parser.add_argument(
        "--server", default="http://127.0.0.1:8000", help="URL del backend"
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="No cerrar la sesión al terminar (para mirar el dashboard)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.15,
        help="Segundos entre votos (usa 1.5 para ver el gráfico en vivo)",
    )
    args = parser.parse_args()

    try:
        raise SystemExit(
            asyncio.run(main(args.server, args.keep_open, args.delay))
        )
    except httpx.ConnectError:
        print(
            f"No se pudo conectar a {args.server}. "
            "¿Está levantado uvicorn?",
            file=sys.stderr,
        )
        raise SystemExit(1)
