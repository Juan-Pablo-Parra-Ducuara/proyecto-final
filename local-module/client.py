
import json
import os
import threading
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path

import socketio


COOKIE_NAME = "clicker_session"

MOTIVOS_RECHAZO = {
    "unknown": "QR no registrado en esta sesión",
    "closed": "La votación está cerrada",
    "invalid": "Opción inválida",
    "stale_session": "La sesión cambió; vuelve a abrir la votación",
}


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


def request_json(url, method="GET", payload=None, headers=None):
    """Hace una petición HTTP sencilla sin dependencias extra."""

    cabeceras = {"Content-Type": "application/json"}
    if headers:
        cabeceras.update(headers)

    cuerpo = (
        json.dumps(payload).encode("utf-8")
        if payload is not None
        else None
    )

    peticion = urllib.request.Request(
        url,
        data=cuerpo,
        headers=cabeceras,
        method=method,
    )

    with urllib.request.urlopen(peticion, timeout=10) as respuesta:
        contenido = respuesta.read() or b"{}"
        return json.loads(contenido), respuesta.headers


class LocalSocketClient:
    """Cliente Socket.IO del módulo local con login de profesor."""

    def __init__(self, server_url=None, on_state_reset=None, password=None):
        load_project_env()

        self.server_url = (
            server_url
            or os.getenv("SERVER_URL")
            or f"http://127.0.0.1:{os.getenv('PORT', '8000')}"
        )

        self.password = password
        self.cookie = None

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

    def login(self, password=None):
        """Inicia sesión como profesor y guarda la cookie firmada."""

        if self.cookie:
            return

        password = password or self.password

        if not password:
            raise RuntimeError("Falta la contraseña del dashboard.")

        try:
            _, cabeceras = request_json(
                f"{self.server_url}/auth/login",
                method="POST",
                payload={"password": password},
            )
        except urllib.error.HTTPError as error:
            if error.code == 401:
                raise RuntimeError("Contraseña incorrecta.") from error
            raise RuntimeError(
                f"No se pudo iniciar sesión: {error.code}"
            ) from error
        except OSError as error:
            raise RuntimeError(
                "No se pudo conectar con el backend. "
                "¿Está levantado el servidor?"
            ) from error

        cookies = SimpleCookie()
        cookies.load(cabeceras.get("Set-Cookie") or "")

        morsel = cookies.get(COOKIE_NAME)

        if morsel is None:
            raise RuntimeError(
                "El servidor no devolvió la cookie de sesión."
            )

        self.cookie = morsel.value
        self.password = None

        print("Sesión iniciada como profesor.")

    def create_desktop_ticket(self):
        """Crea un ticket para abrir el dashboard web ya autenticado."""

        if not self.cookie:
            raise RuntimeError("Falta iniciar sesión para crear el ticket.")

        datos, _ = request_json(
            f"{self.server_url}/auth/desktop-ticket",
            method="POST",
            headers={"Cookie": f"{COOKIE_NAME}={self.cookie}"},
        )

        ticket = datos.get("ticket")

        if not ticket:
            raise RuntimeError("El servidor no devolvió el ticket de acceso.")

        return ticket

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

        @self.sio.on("vote:accepted")
        def vote_accepted(data):
            data = data or {}

            print(
                f"Voto registrado: estudiante {data.get('student_id')} "
                f"→ opción {data.get('option')}"
            )

        @self.sio.on("vote:rejected")
        def vote_rejected(data):
            data = data or {}

            motivo = MOTIVOS_RECHAZO.get(
                data.get("reason"),
                data.get("reason") or "desconocido",
            )

            print(
                f"Voto rechazado. Token: {data.get('qr_token')} | "
                f"Motivo: {motivo}"
            )

        @self.sio.on("results:final")
        def results_final(data):
            print("Resultados finales recibidos.")
            print(data)

    def connect(self, password=None):
        """Inicia sesión y conecta el socket con la cookie del dashboard."""

        if self.connected:
            return

        self.login(password)

        self.sio.connect(
            self.server_url,
            headers={"Cookie": f"{COOKIE_NAME}={self.cookie}"},
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
