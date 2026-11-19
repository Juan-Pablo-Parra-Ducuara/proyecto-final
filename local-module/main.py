
import argparse
import getpass
import sys
import webbrowser
from urllib.parse import quote

import cv2

from client import LocalSocketClient, load_project_env
from detector import QRDetector


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Módulo local de votación por cámara QR"
    )

    parser.add_argument(
        "--server",
        default=None,
        help="URL del servidor. Por defecto usa localhost.",
    )

    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Índice de la cámara. Por defecto: 0.",
    )

    parser.add_argument(
        "--password",
        help=(
            "Contraseña del dashboard. Si se omite, se pide "
            "de forma interactiva."
        ),
    )

    parser.add_argument(
        "--show",
        action="store_true",
        help="Muestra la ventana de la cámara.",
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="No abre el dashboard web en el navegador.",
    )

    return parser.parse_args()


def abrir_dashboard(client):
    """Abre el dashboard web con la sesión ya iniciada."""

    url = client.server_url.rstrip("/")

    try:
        ticket = client.create_desktop_ticket()
        url = f"{url}/?desktop_ticket={quote(ticket, safe='')}"
        print("Abriendo el dashboard web en el navegador (sesión iniciada).")
    except Exception as error:
        print(f"No se pudo preparar el acceso automático: {error}")
        print("Abre el navegador e inicia sesión con la contraseña del dashboard.")

    try:
        webbrowser.open(url)
    except Exception as error:
        print(f"No se pudo abrir el navegador: {error}")
        print(f"Ábrelo manualmente en: {url}")


def main():
    args = parse_arguments()

    load_project_env()

    detector = QRDetector(
        camera_index=args.camera,
    )

    password = args.password or getpass.getpass(
        "Contraseña del dashboard: "
    )

    client = LocalSocketClient(
        server_url=args.server,
        on_state_reset=detector.reset_emitted_votes,
        password=password,
    )

    try:
        print("Iniciando sesión en el dashboard...")
        client.connect()

        if not args.no_browser:
            abrir_dashboard(client)

        print("Abriendo cámara...")
        detector.open_camera()

        print("Módulo de cámara QR iniciado correctamente.")

        while True:
            frame = detector.read_frame()

            votes = detector.detect_votes(frame)

            for qr_token, option in votes:
                client.send_vote(qr_token, option)

            if args.show:
                frame = detector.draw_qr_codes(frame)

                status_text = (
                    "VOTACION ABIERTA"
                    if client.voting_open
                    else "ESPERANDO VOTACION"
                )

                cv2.putText(
                    frame,
                    status_text,
                    (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0) if client.voting_open else (0, 165, 255),
                    2,
                )

                cv2.imshow("Clicker por camara QR", frame)

                if cv2.waitKey(1) & 0xFF == 27:
                    break

    except KeyboardInterrupt:
        print("\nCierre solicitado por el usuario.")

    except Exception as error:
        print(f"\nError en el módulo local: {error}")
        return 1

    finally:
        detector.release_camera()
        client.disconnect()
        print("Módulo local cerrado.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
