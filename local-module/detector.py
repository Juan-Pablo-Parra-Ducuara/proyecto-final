
import time

import cv2
import numpy as np


class QRDetector:
    """
    Detecta códigos QR, extrae el token del estudiante
    y clasifica su orientación.

    Cada QR mantiene su propio estado de estabilidad.
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.camera = None

        self.detector = cv2.QRCodeDetector()

        self.orientations = {
            "A": 0,
            "B": 90,
            "C": 180,
            "D": 270,
        }

        self.tolerance = 25
        self.stability_time = 1.5

        self.states_by_token = {}

        self.last_detections = []
        self.last_status = {}

    def open_camera(self):
        """Abre la cámara."""

        self.camera = cv2.VideoCapture(self.camera_index)

        if not self.camera.isOpened():
            raise RuntimeError("No se pudo abrir la cámara.")

        print("Cámara conectada correctamente.")

    def read_frame(self):
        """Captura un fotograma."""

        if self.camera is None:
            raise RuntimeError("La cámara no está abierta.")

        success, frame = self.camera.read()

        if not success:
            raise RuntimeError("No se pudo capturar el fotograma.")

        return frame

   
def detect_qr_codes(self, frame):
    """Detecta máximo 2 códigos QR simultáneamente."""

    detections = []

    try:
        result = self.detector.detectAndDecodeMulti(frame)

        if result[0]:
            decoded_info = result[1]
            points = result[2]

            for token, corners in zip(decoded_info, points):
                if token and len(detections) < 2:
                    detections.append({
                        "token": token.strip(),
                        "corners": np.array(
                            corners,
                            dtype=np.float32,
                        ),
                    })

    except (cv2.error, TypeError):
        pass

    # Si no se detectó ningún QR mediante lectura múltiple,
    # intentamos detectar uno individual.
    if not detections:
        try:
            token, points, _ = self.detector.detectAndDecode(frame)

            if token and points is not None:
                detections.append({
                    "token": token.strip(),
                    "corners": np.array(
                        points[0],
                        dtype=np.float32,
                    ),
                })

        except (cv2.error, TypeError):
            pass

    return detections


    def calculate_angle(self, corners):
        """
        Calcula el ángulo de la primera arista detectada del QR.

        La correspondencia entre esta dirección y la orientación
        real de la respuesta debe calibrarse con pruebas de cámara.
        """

        point_1 = corners[0]
        point_2 = corners[1]

        dx = point_2[0] - point_1[0]
        dy = point_2[1] - point_1[1]

        angle = np.degrees(np.arctan2(dy, dx))

        return angle % 360

    def classify_orientation(self, angle):
        """Clasifica la orientación más cercana."""

        best_orientation = None
        smallest_difference = float("inf")

        for letter, target_angle in self.orientations.items():
            difference = abs(angle - target_angle)
            difference = min(difference, 360 - difference)

            if difference < smallest_difference:
                smallest_difference = difference
                best_orientation = letter

        if smallest_difference <= self.tolerance:
            return best_orientation

        return None

    def _update_qr_state(self, token, orientation, current_time):
        """Comprueba si una orientación permanece estable."""

        if token not in self.states_by_token:
            self.states_by_token[token] = {
                "candidate": None,
                "candidate_since": None,
                "confirmed": None,
                "last_emitted": None,
                "last_seen": current_time,
            }

        state = self.states_by_token[token]
        state["last_seen"] = current_time

        if orientation is None:
            state["candidate"] = None
            state["candidate_since"] = None
            return None, 0.0

        if orientation != state["candidate"]:
            state["candidate"] = orientation
            state["candidate_since"] = current_time

        elapsed = current_time - state["candidate_since"]

        if elapsed >= self.stability_time:
            state["confirmed"] = orientation

            if orientation != state["last_emitted"]:
                state["last_emitted"] = orientation
                return orientation, elapsed

        return None, elapsed

    def _clean_inactive_states(self, present_tokens, current_time):
        """Limpia estados de QR que llevan tiempo ausentes."""

        for token in list(self.states_by_token.keys()):
            state = self.states_by_token[token]

            inactive_time = current_time - state["last_seen"]

            if token not in present_tokens and inactive_time > 0.5:
                state["candidate"] = None
                state["candidate_since"] = None

            if inactive_time > 10:
                del self.states_by_token[token]

    def detect_votes(self, frame):
        """
        Devuelve una lista de:
        (qr_token, option).

        Solo genera un voto cuando el QR permanece estable
        durante el tiempo configurado.
        """

        detections = self.detect_qr_codes(frame)

        self.last_detections = detections
        self.last_status = {}

        current_time = time.monotonic()
        votes = []
        present_tokens = set()

        for detection in detections:
            token = detection["token"]
            corners = detection["corners"]

            present_tokens.add(token)

            angle = self.calculate_angle(corners)
            orientation = self.classify_orientation(angle)

            new_vote, elapsed = self._update_qr_state(
                token,
                orientation,
                current_time,
            )

            state = self.states_by_token[token]

            self.last_status[token] = {
                "angle": angle,
                "orientation": orientation,
                "confirmed": state["confirmed"],
                "elapsed": elapsed,
            }

            if new_vote is not None:
                votes.append((token, new_vote))

        self._clean_inactive_states(present_tokens, current_time)

        return votes

    def draw_qr_codes(self, frame):
        """Dibuja los QR detectados y su estado."""

        for detection in self.last_detections:
            token = detection["token"]
            corners = detection["corners"].astype(int)

            status = self.last_status.get(token)

            if status is None:
                continue

            cv2.polylines(
                frame,
                [corners.reshape((-1, 1, 2))],
                True,
                (0, 255, 0),
                3,
            )

            center = corners.mean(axis=0).astype(int)

            angle = status["angle"]
            orientation = status["orientation"]
            confirmed = status["confirmed"]
            elapsed = status["elapsed"]

            cv2.putText(
                frame,
                f"QR: {token[:12]}...",
                (center[0] - 100, center[1] - 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 0),
                2,
            )

            if orientation is None:
                message = f"Angulo: {angle:.1f} - No reconocido"

            elif confirmed == orientation:
                message = f"Respuesta: {confirmed} - CONFIRMADA"

            else:
                remaining = max(0, self.stability_time - elapsed)
                message = f"Detectando {orientation}: {remaining:.1f}s"

            cv2.putText(
                frame,
                message,
                (center[0] - 100, center[1] + 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 0, 0),
                2,
            )

        return frame

    def reset_emitted_votes(self):
        """Permite volver a enviar votos en una nueva sesión."""

        for state in self.states_by_token.values():
            state["last_emitted"] = None

    def release_camera(self):
        """Libera la cámara y cierra las ventanas."""

        if self.camera is not None:
            self.camera.release()
            self.camera = None

        cv2.destroyAllWindows()


if __name__ == "__main__":
    detector = QRDetector()

    try:
        detector.open_camera()

        while True:
            frame = detector.read_frame()

            votes = detector.detect_votes(frame)

            if votes:
                print("Nuevos votos:", votes)

            frame = detector.draw_qr_codes(frame)

            cv2.imshow("Camara - Proyecto QR", frame)

            if cv2.waitKey(1) & 0xFF == 27:
                break

    except RuntimeError as error:
        print(f"Error: {error}")

    finally:
        detector.release_camera()
