import secrets

from pwdlib import PasswordHash
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from .schemas import (
    QuestionCreate,
    QuestionRead,
    SessionCreate,
    StudentAccountCreate,
    StudentCreate,
    StudentRead,
)
from . import services
from .auth import require_dashboard
from .db import get_session
from .models import Question, Student
from .schemas import (
    QuestionCreate,
    QuestionRead,
    SessionCreate,
    StudentCreate,
    StudentRead,
)
from .sockets import sio

router = APIRouter(tags=["api"])
protegido = [Depends(require_dashboard)]
password_hash = PasswordHash.recommended()

@router.post(
    "/students",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=protegido,
)
async def crear_estudiante(
    payload: StudentCreate, db: AsyncSession = Depends(get_session)
) -> Student:
    student = Student(name=payload.name, aruco_id=payload.aruco_id)
    db.add(student)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El aruco_id ya está registrado",
        )
    await db.refresh(student)
    return student


@router.post(
    "/students/accounts",
    status_code=status.HTTP_201_CREATED,
    dependencies=protegido,
)
@router.post(
    "/students/accounts",
    status_code=status.HTTP_201_CREATED,
    dependencies=protegido,
)
async def crear_cuenta_estudiante(
    payload: StudentAccountCreate,
    db: AsyncSession = Depends(get_session),
) -> dict:

    email = payload.email.strip().lower()

    # Comprobar que el correo no esté registrado.
    result = await db.execute(
        select(Student).where(Student.email == email)
    )

    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="El correo electrónico ya está registrado",
        )

    # Generar identificador interno compatible con el campo antiguo.
    result = await db.execute(
        select(func.max(Student.aruco_id))
    )

    ultimo_aruco_id = result.scalar() or 0
    identificador_legacy = ultimo_aruco_id + 1

    # Generar un QR único y permanente.
    qr_token = secrets.token_urlsafe(32)

    student = Student(
    name=payload.name.strip(),
    aruco_id=identificador_legacy,
    email=email,
    password_hash=password_hash.hash(payload.password),
    qr_token=qr_token,
)
    db.add(student)

    try:
        await db.commit()
        await db.refresh(student)

    except IntegrityError:
        await db.rollback()

        raise HTTPException(
            status_code=409,
            detail="No se pudo crear la cuenta. Comprueba que el correo no esté registrado.",
        )

    return {
        "id": student.id,
        "name": student.name,
        "email": student.email,
        "created_at": student.created_at,
        "message": "Cuenta estudiantil creada correctamente",
    }


@router.get(
    "/students", response_model=list[StudentRead], dependencies=protegido
)
async def listar_estudiantes(
    db: AsyncSession = Depends(get_session),
) -> list[Student]:
    result = await db.execute(select(Student).order_by(Student.aruco_id))
    return list(result.scalars().all())

@router.get(
    "/questions/{question_id}/results/latest",
    dependencies=protegido
)
async def resultados_ultima_sesion(question_id: int):
    try:
        results = await services.get_latest_question_results(question_id)

        if results is None:
            raise HTTPException(
                404,
                detail="Esta pregunta todavía no tiene resultados"
            )

        return results

    except LookupError:
        raise HTTPException(
            404,
            detail="Pregunta no encontrada"
        )

@router.delete(
    "/questions/{question_id}/answers",
    dependencies=protegido
)
async def borrar_respuestas_pregunta(question_id: int):
    try:
        resultado = await services.clear_question_answers(question_id)

        # Si la pregunta sigue abierta, actualizar el dashboard en vivo.
        if resultado["tally"] is not None:
            await sio.emit(
                "tally:update",
                resultado["tally"],
                room="dashboard"
            )

        return {
            "message": "Respuestas eliminadas correctamente",
            "deleted_votes": resultado["deleted_votes"],
            "question_id": question_id
        }

    except LookupError:
        raise HTTPException(
            404,
            detail="Pregunta no encontrada"
        )

@router.delete(
    "/students/{student_id}",
    dependencies=protegido
)
async def borrar_estudiante(student_id: int):
    try:
        resultado = await services.remove_student(student_id)

        # Actualizar los resultados de la sesión activa.
        if resultado["tally"] is not None:
            await sio.emit(
                "tally:update",
                resultado["tally"],
                room="dashboard"
            )

        return {
    "message": "Estudiante eliminado correctamente",
    "student_id": resultado["student_id"],
    "tally": resultado["tally"]
}

    except LookupError:
        raise HTTPException(
            status_code=404,
            detail="Estudiante no encontrado"
        )


@router.delete(
    "/questions/{question_id}",
    dependencies=protegido
)
async def borrar_pregunta(question_id: int):
    try:
        resultado = await services.remove_question(question_id)

        # Si se eliminó la pregunta de la sesión activa,
        # notificar que la votación debe cerrarse.
        if resultado["active_session_deleted"]:
            evento = {
                "session_id": resultado["active_session_id"]
            }

            await sio.emit(
                "vote:close",
                evento,
                room="local"
            )
            await sio.emit(
                "vote:close",
                evento,
                room="dashboard"
            )

        return {
            "message": "Pregunta eliminada correctamente",
            "question_id": resultado["question_id"],
            "deleted_sessions": resultado["deleted_sessions"]
        }

    except LookupError:
        raise HTTPException(
            status_code=404,
            detail="Pregunta no encontrada"
        )

@router.post("/students/bulk", dependencies=protegido)
async def cargar_estudiantes(
    payload: list[StudentCreate], db: AsyncSession = Depends(get_session)
) -> dict:
    por_aruco = {item.aruco_id: item for item in payload}
    if not por_aruco:
        return {"count": 0}

    values = [
        {"name": item.name, "aruco_id": item.aruco_id}
        for item in por_aruco.values()
    ]
    stmt = pg_insert(Student).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["aruco_id"],
        set_={"name": stmt.excluded.name},
    )
    await db.execute(stmt)
    await db.commit()
    return {"count": len(values)}


@router.post(
    "/questions",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=protegido,
)
async def crear_pregunta(
    payload: QuestionCreate, db: AsyncSession = Depends(get_session)
) -> Question:
    question = Question(**payload.model_dump())
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


@router.get(
    "/questions", response_model=list[QuestionRead], dependencies=protegido
)
async def listar_preguntas(
    db: AsyncSession = Depends(get_session),
) -> list[Question]:
    result = await db.execute(select(Question).order_by(Question.id.asc()))
    return list(result.scalars().all())


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    dependencies=protegido,
)
async def abrir_sesion(payload: SessionCreate) -> dict:
    try:
        session_id, evento = await services.open_session(payload.question_id)
    except ValueError as exc:
        if str(exc) == "question_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La pregunta no existe",
            )
        if str(exc) == "session_already_open":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya hay una sesión de votación abierta",
            )
        raise

    await sio.emit("vote:open", evento, room="local")
    await sio.emit("vote:open", evento, room="dashboard")
    return {"session_id": session_id, "status": "open"}


@router.post("/sessions/{session_id}/close", dependencies=protegido)
async def cerrar_sesion(session_id: int) -> dict:
    try:
        results = await services.close_session(session_id)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La sesión no existe",
        )

    evento = {"session_id": session_id}
    await sio.emit("vote:close", evento, room="local")
    await sio.emit("vote:close", evento, room="dashboard")
    await sio.emit("results:final", results, room="local")
    await sio.emit("results:final", results, room="dashboard")
    return results


@router.get("/sessions/active", dependencies=protegido)
async def sesion_activa() -> dict:
    return await services.build_state_sync()


@router.get("/sessions/{session_id}/results", dependencies=protegido)
async def resultados_sesion(session_id: int) -> dict:
    try:
        return await services.get_results(session_id)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La sesión no existe",
        )
