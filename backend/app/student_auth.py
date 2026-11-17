from .services import build_student_state
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pwdlib import PasswordHash

from .auth import (
    clear_student_session_cookie,
    require_student,
    set_student_session_cookie,
)
from .db import get_session
from .models import Student
from .schemas import StudentLoginRequest, StudentMe

router = APIRouter(prefix="/student-auth", tags=["student-auth"])

password_hash = PasswordHash.recommended()


@router.post("/login")
async def student_login(
    payload: StudentLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> dict:
    email = payload.email.strip().lower()

    result = await db.execute(
        select(Student).where(Student.email == email)
    )
    student = result.scalar_one_or_none()

    if (
        student is None
        or student.password_hash is None
        or not password_hash.verify(
            payload.password,
            student.password_hash,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )

    set_student_session_cookie(response, request, student.id)

    return {"ok": True, "role": "student"}


@router.post("/logout")
async def student_logout(response: Response) -> dict:
    clear_student_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=StudentMe)
async def student_me(
    student_id: int = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> Student:
    result = await db.execute(
        select(Student).where(Student.id == student_id)
    )
    student = result.scalar_one_or_none()

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La cuenta de estudiante ya no existe",
        )

    return student


@router.get("/panel")
async def student_panel(
    student_id: int = Depends(require_student),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await db.execute(
        select(Student).where(Student.id == student_id)
    )
    student = result.scalar_one_or_none()

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La cuenta de estudiante ya no existe",
        )

    state = await build_student_state(student_id)

    return {
        "student": {
            "id": student.id,
            "name": student.name,
        },
        "qr_token": student.qr_token,
        "voting_status": state["voting_status"],
        "session_id": state.get("session_id"),
        "question": state.get("question"),
        "options": state.get("options"),
        "your_vote": state.get("your_vote"),
    }
