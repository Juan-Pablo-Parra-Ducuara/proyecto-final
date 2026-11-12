import secrets
from http.cookies import SimpleCookie

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import get_settings
from .schemas import LoginRequest

COOKIE_NAME = "clicker_session"
SESSION_MAX_AGE = 12 * 60 * 60

STUDENT_COOKIE_NAME = "clicker_student_session"

router = APIRouter(prefix="/auth", tags=["auth"])


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().secret_key, salt="clicker-dashboard-session"
    )


def create_session_cookie() -> str:
    return _serializer().dumps({"role": "dashboard"})


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
    return secrets.compare_digest(password, get_settings().dashboard_password)


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


def role_from_environ(environ: dict, auth: dict | None) -> str | None:
    auth = auth or {}
    if auth.get("role") == "local":
        key = str(auth.get("api_key") or "")
        if secrets.compare_digest(key, get_settings().api_key):
            return "local"
        return None

    cookie_header = environ.get("HTTP_COOKIE", "")
    if cookie_header:
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        morsel = cookies.get(COOKIE_NAME)
        if morsel is not None and verify_session_cookie(morsel.value):
            return "dashboard"
    return None


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    if not verify_password(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Contraseña incorrecta"
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
