
import os
import time

import cv2
import numpy as np


class ArucoDetector:
    """
    Detecta marcadores ArUco y reconoce su orientación.
    Cada marcador mantiene su propio estado de estabilidad.
    """

    def __init__(
        self,
        camera_index: int = 0,
        aruco_dict_name: str | None = None
    ):
        self.camera_index = camera_index
        self.camera = None

        # Diccionario configurable desde el archivo .env
        aruco_dict_name = (
            aruco_dict_name
            or os.getenv("ARUCO_DICT", "DICT_4X4_50")
        )

        if not hasattr(cv2.aruco, aruco_dict_name):
            raise ValueError(
                f"Diccionario ArUco no válido: {aruco_dict_name}"
            )

        self.aruco_dict = cv2.aruco.getPredefinedDictionary(
            getattr(cv2.aruco, aruco_dict_name)
        )

        self.parameters = cv2.aruco.DetectorParameters()

        self.detector = cv2.aruco.ArucoDetector(
            self.aruco_dict,
            self.parameters
        )

        # Orientaciones permitidas
        self.orientations = {
            "A": 0,
            "B": 90,
            "C": 180,
            "D": 270
        }

        self.tolerance = 15
        self.stability_time = 1.5

        # Estado independiente para cada ID
        self.states_by_id = {}

        # Últimas detecciones, utilizadas para dibujar en pantalla
        self.last_corners = []
        self.last_ids = None
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

    def detect_markers(self, frame):
        """Detecta los marcadores ArUco presentes."""

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        corners, ids, _ = self.detector.detectMarkers(gray)

        return corners, ids

    def calculate_angle(self, marker_corners):
        """Calcula el ángulo de rotación del marcador."""

        points = marker_corners[0]

        point_1 = points[0]
        point_2 = points[1]

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

    def _update_marker_state(self, marker_id, orientation, current_time):
        """
        Actualiza la estabilidad de un marcador sin afectar a los demás.
        Devuelve una opción únicamente cuando se estabiliza y es nueva.
        """

        if marker_id not in self.states_by_id:
            self.states_by_id[marker_id] = {
                "candidate": None,
                "candidate_since": None,
                "confirmed": None,
                "last_emitted": None,
                "last_seen": current_time
            }

        state = self.states_by_id[marker_id]
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

            # Solo genera un voto cuando la respuesta cambia
            if orientation != state["last_emitted"]:
                state["last_emitted"] = orientation
                return orientation, elapsed

        return None, elapsed

    def _clean_inactive_states(self, present_ids, current_time):
        """Limpia estados de marcadores que llevan tiempo ausentes."""

        for marker_id in list(self.states_by_id.keys()):

            state = self.states_by_id[marker_id]
            inactive_time = current_time - state["last_seen"]

            # Si desaparece brevemente, reinicia el tiempo de estabilidad
            if marker_id not in present_ids and inactive_time > 0.5:
                state["candidate"] = None
                state["candidate_since"] = None

            # Elimina estados que llevan mucho tiempo sin aparecer
            if inactive_time > 10:
                del self.states_by_id[marker_id]

    def detect_votes(self, frame):
        """
        Detecta votos estables y devuelve una lista de:
        (aruco_id, option).

        Un marcador solo genera un nuevo voto cuando su orientación
        permanece estable durante el tiempo configurado.
        """

        corners, ids = self.detect_markers(frame)

        self.last_corners = corners
        self.last_ids = ids
        self.last_status = {}

        current_time = time.monotonic()
        votes = []
        present_ids = set()

        if ids is not None:

            for index, marker_id in enumerate(ids.flatten()):

                marker_id = int(marker_id)
                present_ids.add(marker_id)

                angle = self.calculate_angle(corners[index])
                orientation = self.classify_orientation(angle)

                new_vote, elapsed = self._update_marker_state(
                    marker_id,
                    orientation,
                    current_time
                )

                state = self.states_by_id[marker_id]

                self.last_status[marker_id] = {
                    "angle": angle,
                    "orientation": orientation,
                    "confirmed": state["confirmed"],
                    "elapsed": elapsed
                }

                if new_vote is not None:
                    votes.append((marker_id, new_vote))

        self._clean_inactive_states(present_ids, current_time)

        return votes

    def draw_markers(self, frame, corners=None, ids=None):
        """Dibuja los marcadores y su estado de reconocimiento."""

        if corners is None:
            corners = self.last_corners

        if ids is None:
            ids = self.last_ids

        if ids is not None:

            cv2.aruco.drawDetectedMarkers(frame, corners, ids)

            for index, marker_id in enumerate(ids.flatten()):

                marker_id = int(marker_id)

                center = corners[index][0].mean(axis=0).astype(int)

                status = self.last_status.get(marker_id)

                if status is None:
                    continue

                angle = status["angle"]
                orientation = status["orientation"]
                confirmed = status["confirmed"]
                elapsed = status["elapsed"]

                cv2.putText(
                    frame,
                    f"ID: {marker_id} | Angulo: {angle:.1f}",
                    (center[0] - 100, center[1] - 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2
                )

                if orientation is None:
                    message = "Orientacion no reconocida"

                elif confirmed == orientation:
                    message = f"Orientacion: {confirmed} - CONFIRMADA"

                else:
                    remaining = max(0, self.stability_time - elapsed)
                    message = f"Detectando {orientation}: {remaining:.1f}s"

                cv2.putText(
                    frame,
                    message,
                    (center[0] - 100, center[1] + 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (255, 0, 0),
                    2
                )

        return frame

    def reset_emitted_votes(self):
        """
        Permite volver a enviar votos después de una nueva sincronización
        o apertura de sesión.
        """

        for state in self.states_by_id.values():
            state["last_emitted"] = None

    def release_camera(self):
        """Libera la cámara y cierra las ventanas."""

        if self.camera is not None:
            self.camera.release()
            self.camera = None

        cv2.destroyAllWindows()


if __name__ == "__main__":

    camera_detector = ArucoDetector()

    try:
        camera_detector.open_camera()

        while True:

            frame = camera_detector.read_frame()

            votes = camera_detector.detect_votes(frame)

            if votes:
                print("Nuevos votos:", votes)

            frame = camera_detector.draw_markers(frame)

            cv2.imshow("Camara - Proyecto ArUco", frame)

            if cv2.waitKey(1) & 0xFF == 27:
                break

    except RuntimeError as error:
        print(f"Error: {error}")

    finally:
        camera_detector.release_camera()
