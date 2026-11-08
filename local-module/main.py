
import argparse
import sys

import cv2

from client import LocalSocketClient, load_project_env
from detector import ArucoDetector


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Módulo local de votación por cámara ArUco"
    )

    parser.add_argument(
        "--server",
        default=None,
        help="URL del servidor. Por defecto usa localhost."
    )

    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Índice de la cámara. Por defecto: 0."
    )

    parser.add_argument(
        "--show",
        action="store_true",
        help="Muestra la ventana de la cámara."
    )

    return parser.parse_args()


def main():
    args = parse_arguments()

    load_project_env()

    detector = ArucoDetector(
        camera_index=args.camera
    )

    client = LocalSocketClient(
        server_url=args.server,
        on_state_reset=detector.reset_emitted_votes
    )

    try:
        print("Conectando con el servidor...")
        client.connect()

        print("Abriendo cámara...")
        detector.open_camera()

        print("Módulo de cámara iniciado correctamente.")

        while True:
            frame = detector.read_frame()

            # Detectar marcadores y respuestas estables
            votes = detector.detect_votes(frame)

            # Enviar los nuevos votos al backend
            for aruco_id, option in votes:
                client.send_vote(aruco_id, option)

            # Dibujar información de los marcadores
            if args.show:
                frame = detector.draw_markers(frame)

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
                    2
                )

                cv2.imshow("Clicker por camara", frame)

                # ESC para cerrar
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
