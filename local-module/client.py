
import os
import threading
from pathlib import Path

import socketio


def load_project_env():
    """Carga las variables del archivo .env de la raíz del proyecto."""

    env_path = Path(__file__).resolve().parents[1] / ".env"

    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            os.environ.setdefault(key, value)


class LocalSocketClient:
    """Cliente Socket.IO del módulo local de cámara QR."""

    def __init__(self, server_url=None, on_state_reset=None):
        load_project_env()

        self.server_url = (
            server_url
            or os.getenv("SERVER_URL")
            or f"http://127.0.0.1:{os.getenv('PORT', '8000')}"
        )

        self.api_key = os.getenv("API_KEY", "")

        if not self.api_key:
            raise RuntimeError(
                "No se encontró API_KEY. Revisa el archivo .env."
            )

        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,
            reconnection_delay=1,
            reconnection_delay_max=5,
        )

        self.connected = False
        self.voting_open = False
        self.session_id = None
        self.roster = set()

        self.lock = threading.Lock()
        self.on_state_reset = on_state_reset

        self._register_events()

    def _reset_detector(self):
        """Notifica al detector que debe permitir nuevos envíos."""

        if self.on_state_reset:
            self.on_state_reset()

    def _register_events(self):
        """Registra los eventos recibidos desde el backend."""

        @self.sio.event
        def connect():
            with self.lock:
                self.connected = True

            print("Conectado al servidor Socket.IO.")

        @self.sio.event
        def disconnect():
            with self.lock:
                self.connected = False
                self.voting_open = False
                self.session_id = None

            print("Desconectado del servidor.")

        @self.sio.event
        def connect_error(data):
            print(f"Error de conexión: {data}")

        @self.sio.on("state:sync")
        def state_sync(data):
            data = data or {}

            is_open = data.get("status") == "open"
            session_id = data.get("session_id")

            roster = {
                int(student_id)
                for student_id in data.get("roster", [])
            }

            with self.lock:
                self.voting_open = is_open
                self.session_id = session_id if is_open else None
                self.roster = roster if is_open else set()

            self._reset_detector()

            if is_open:
                print(f"Votación activa. Sesión: {session_id}")
                print(f"Estudiantes habilitados: {len(roster)}")
            else:
                print("No hay ninguna votación abierta.")

        @self.sio.on("vote:open")
        def vote_open(data):
            data = data or {}

            session_id = int(data["session_id"])

            roster = {
                int(student_id)
                for student_id in data.get("roster", [])
            }

            with self.lock:
                self.session_id = session_id
                self.voting_open = True
                self.roster = roster

            self._reset_detector()

            print(f"Votación abierta. Sesión: {session_id}")
            print(f"Estudiantes habilitados: {len(roster)}")

        @self.sio.on("vote:close")
        def vote_close(data):
            data = data or {}
            received_session = data.get("session_id")

            with self.lock:
                if (
                    received_session is not None
                    and int(received_session) == self.session_id
                ):
                    self.voting_open = False

            self._reset_detector()

            print("La votación ha sido cerrada.")

        @self.sio.on("vote:rejected")
        def vote_rejected(data):
            data = data or {}

            print(
                f"Voto rechazado. Token: {data.get('qr_token')} | "
                f"Motivo: {data.get('reason')}"
            )

        @self.sio.on("results:final")
        def results_final(data):
            print("Resultados finales recibidos.")
            print(data)

    def connect(self):
        """Conecta y autentica el cliente ante el backend."""

        if self.connected:
            return

        self.sio.connect(
            self.server_url,
            auth={
                "role": "local",
                "api_key": self.api_key,
            },
            transports=["websocket"],
            wait_timeout=10,
        )

    def send_vote(self, qr_token, option):
        """Envía un voto usando el token QR del estudiante."""

        qr_token = str(qr_token).strip()
        option = str(option).upper()

        with self.lock:
            if not self.connected:
                return False

            if not self.voting_open or self.session_id is None:
                return False

            if not qr_token:
                print("Token QR vacío. Voto no enviado.")
                return False

            if option not in {"A", "B", "C", "D"}:
                print("Opción inválida. Voto no enviado.")
                return False

            payload = {
                "session_id": self.session_id,
                "qr_token": qr_token,
                "option": option,
            }

        self.sio.emit("vote:cast", payload)

        print(f"Voto enviado: QR {qr_token[:8]}... -> {option}")
        return True

    def disconnect(self):
        """Cierra la conexión Socket.IO."""

        if self.sio.connected:
            self.sio.disconnect()
