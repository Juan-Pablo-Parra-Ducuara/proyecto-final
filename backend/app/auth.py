import secrets
from http.cookies import SimpleCookie

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings
from .schemas import DesktopLoginRequest, LoginRequest

COOKIE_NAME = "clicker_session"
SESSION_MAX_AGE = 12 * 60 * 60

# El módulo local crea un ticket breve para abrir el dashboard ya logueado.
DESKTOP_TICKET_MAX_AGE = 120
_tickets_de_escritorio_usados: set[str] = set()

STUDENT_COOKIE_NAME = "clicker_student_session"

router = APIRouter(prefix="/auth", tags=["auth"])


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key, salt="clicker-dashboard-session"
    )


def create_session_cookie() -> str:
    return _serializer().dumps({"role": "dashboard"})


def _desktop_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key, salt="clicker-desktop-login"
    )


def create_desktop_ticket() -> str:
    """Genera un ticket de un solo uso para el login del módulo local."""

    return _desktop_serializer().dumps({
        "role": "dashboard",
        "nonce": secrets.token_hex(8),
    })


def consume_desktop_ticket(ticket: str) -> bool:
    """Valida el ticket y lo marca como usado para evitar reutilizaciones."""

    try:
        data = _desktop_serializer().loads(
            ticket, max_age=DESKTOP_TICKET_MAX_AGE
        )
    except (BadSignature, SignatureExpired):
        return False

    if data.get("role") != "dashboard":
        return False

    if ticket in _tickets_de_escritorio_usados:
        return False

    _tickets_de_escritorio_usados.add(ticket)
    return True


def _student_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key,
        salt="clicker-student-session",
    )


def create_student_session_cookie(student_id: int) -> str:
    return _student_serializer().dumps({
        "role": "student",
        "student_id": student_id,
    })


def verify_student_session_cookie(value: str | None) -> int | None:
    if not value:
        return None

    try:
        data = _student_serializer().loads(
            value,
            max_age=SESSION_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        return None

    if data.get("role") != "student":
        return None

    student_id = data.get("student_id")

    if not isinstance(student_id, int) or student_id <= 0:
        return None

    return student_id


def set_student_session_cookie(
    response: Response,
    request: Request,
    student_id: int,
) -> None:
    response.set_cookie(
        STUDENT_COOKIE_NAME,
        create_student_session_cookie(student_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def clear_student_session_cookie(response: Response) -> None:
    response.delete_cookie(STUDENT_COOKIE_NAME)


async def require_student(request: Request) -> int:
    student_id = verify_student_session_cookie(
        request.cookies.get(STUDENT_COOKIE_NAME)
    )

    if student_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión de estudiante no válida",
        )

    return student_id

def verify_session_cookie(value: str | None) -> bool:
    if not value:
        return False
    try:
        data = _serializer().loads(value, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return data.get("role") == "dashboard"


def verify_password(password: str) -> bool:
    # compare_digest solo admite ASCII en strings; codificamos a bytes para
    # soportar contraseñas con tildes o caracteres no ASCII.
    return secrets.compare_digest(
        password.encode("utf-8"),
        get_settings().dashboard_password.encode("utf-8"),
    )


def set_session_cookie(response: Response, request: Request) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_session_cookie(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


async def require_dashboard(request: Request) -> None:
    if not verify_session_cookie(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No autorizado"
        )


def socket_context_from_environ(
    environ: dict, auth: dict | None
) -> dict | None:
    """Identifica al cliente del socket y devuelve su contexto de sesión.

    El módulo local, el dashboard y el estudiante usan cookies firmadas. La
    API key se acepta solo como compatibilidad legacy. El contexto del
    estudiante incluye su id para poder aislarlo en una sala privada.
    """

    auth = auth or {}

    if auth.get("role") == "local":
        key = str(auth.get("api_key") or "")
        if secrets.compare_digest(key, get_settings().api_key):
            return {"role": "local"}
        return None

    cookie_header = environ.get("HTTP_COOKIE", "")

    if not cookie_header:
        return None

    cookies = SimpleCookie()
    cookies.load(cookie_header)

    morsel = cookies.get(COOKIE_NAME)

    if morsel is not None and verify_session_cookie(morsel.value):
        return {"role": "dashboard"}

    student_morsel = cookies.get(STUDENT_COOKIE_NAME)

    student_id = verify_student_session_cookie(
        student_morsel.value if student_morsel is not None else None
    )

    if student_id is not None:
        return {"role": "student", "student_id": student_id}

    return None


def role_from_environ(environ: dict, auth: dict | None) -> str | None:
    context = socket_context_from_environ(environ, auth)
    return context["role"] if context is not None else None


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    if not verify_password(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Contraseña incorrecta"
        )
    set_session_cookie(response, request)
    return {"ok": True, "role": "dashboard"}


@router.post("/desktop-ticket", dependencies=[Depends(require_dashboard)])
async def desktop_ticket() -> dict:
    """Crea el ticket usado por el módulo local al abrir el navegador."""

    return {"ticket": create_desktop_ticket()}


@router.post("/desktop-login")
async def desktop_login(
    payload: DesktopLoginRequest,
    request: Request,
    response: Response,
) -> dict:
    """Canjea el ticket del módulo local por la cookie del dashboard."""

    if not consume_desktop_ticket(payload.ticket):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ticket no válido o caducado",
        )

    set_session_cookie(response, request)
    return {"ok": True, "role": "dashboard"}


@router.post("/logout")
async def logout(response: Response) -> dict:
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", dependencies=[Depends(require_dashboard)])
async def me() -> dict:
    return {"role": "dashboard"}
