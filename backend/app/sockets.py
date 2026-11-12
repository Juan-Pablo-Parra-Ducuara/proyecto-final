import socketio

from . import services
from .auth import role_from_environ

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None) -> None:
    role = role_from_environ(environ, auth)

    if role is None:
        raise ConnectionRefusedError("no autorizado")

    await sio.save_session(sid, {"role": role})
    await sio.enter_room(sid, role)

    await sio.emit(
        "state:sync",
        await services.build_state_sync(),
        to=sid,
    )


@sio.on("vote:cast")
async def vote_cast(sid: str, data: dict | None) -> None:
    try:
        session = await sio.get_session(sid)
    except KeyError:
        return

    if session.get("role") != "local":
        return

    data = data or {}

    try:
        session_id = int(data["session_id"])
        qr_token = str(data["qr_token"])
        option = str(data["option"])
    except (KeyError, TypeError, ValueError):
        await sio.emit(
            "vote:rejected",
            {
                "qr_token": data.get("qr_token"),
                "reason": "invalid",
            },
            to=sid,
        )
        return

    ok, reason, tally = await services.cast_vote(
        session_id,
        qr_token,
        option,
    )

    if not ok:
        await sio.emit(
            "vote:rejected",
            {
                "qr_token": qr_token,
                "reason": reason,
            },
            to=sid,
        )
        return

    await sio.emit(
        "tally:update",
        tally,
        room="dashboard",
    )