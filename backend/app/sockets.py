import socketio

from . import services
from .auth import socket_context_from_environ

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)

# Roles que pueden enviar votos: el módulo local (cámara del PC) y el
# dashboard (escáner QR desde la cámara del teléfono).
VOTE_CAST_ROLES = {"local", "dashboard"}


async def _reject(
    sid: str,
    data: dict,
    reference_key: str | None,
    reason: str,
) -> None:
    """Notifica un voto rechazado conservando el identificador recibido."""

    payload = {"reason": reason}

    if reference_key is not None and reference_key in data:
        payload[reference_key] = data[reference_key]

    await sio.emit("vote:rejected", payload, to=sid)


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None) -> None:
    context = socket_context_from_environ(environ, auth)

    if context is None:
        raise ConnectionRefusedError("no autorizado")

    await sio.save_session(sid, context)

    role = context["role"]

    if role == "student":
        student_id = context["student_id"]

        # Sala privada para avisos personales + sala común para el estado.
        await sio.enter_room(sid, f"student:{student_id}")
        await sio.enter_room(sid, "students")

        payload = await services.build_student_state(student_id)
    else:
        await sio.enter_room(sid, role)
        payload = await services.build_state_sync()

    await sio.emit("state:sync", payload, to=sid)


@sio.on("vote:cast")
async def vote_cast(sid: str, data: dict | None) -> None:
    try:
        session = await sio.get_session(sid)
    except KeyError:
        return

    if session.get("role") not in VOTE_CAST_ROLES:
        return

    data = data or {}

    reference_key = None

    if data.get("qr_token"):
        reference_key = "qr_token"
    elif data.get("aruco_id") is not None:
        reference_key = "aruco_id"

    try:
        session_id = int(data["session_id"])
    except (KeyError, TypeError, ValueError):
        await _reject(sid, data, reference_key, "invalid")
        return

    if reference_key is None:
        await _reject(sid, data, reference_key, "invalid")
        return

    option = str(data.get("option") or "")

    ok, reason, tally, student_id = await services.cast_vote(
        session_id,
        data[reference_key],
        option,
    )

    if not ok:
        await _reject(sid, data, reference_key, reason)
        return

    accepted = {
        "session_id": session_id,
        "student_id": student_id,
        "option": option.upper(),
    }

    # El estudiante ve el acuse en su panel; el escáner lo registra en pantalla.
    await sio.emit("vote:accepted", accepted, room=f"student:{student_id}")
    await sio.emit("vote:accepted", accepted, to=sid)

    await sio.emit(
        "tally:update",
        tally,
        room="dashboard",
    )
