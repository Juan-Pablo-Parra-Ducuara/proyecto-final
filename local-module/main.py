
import argparse
import sys

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
        "--show",
        action="store_true",
        help="Muestra la ventana de la cámara.",
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    load_project_env()

    detector = QRDetector(
        camera_index=args.camera,
    )

    client = LocalSocketClient(
        server_url=args.server,
        on_state_reset=detector.reset_emitted_votes,
    )

    try:
        print("Conectando con el servidor...")
        client.connect()

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
