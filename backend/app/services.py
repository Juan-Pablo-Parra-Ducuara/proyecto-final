from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import SessionLocal
from .models import Question, Student, Vote, VotingSession
from .redis_client import redis_client

VALID_OPTIONS = {"A", "B", "C", "D"}
ACTIVE_SESSION_KEY = "active_session"


def votes_key(session_id: int) -> str:
    return f"session:{session_id}:votes"


def roster_key(session_id: int) -> str:
    return f"session:{session_id}:roster"


def counts_key(session_id: int) -> str:
    return f"session:{session_id}:counts"


def _question_payload(question: Question) -> dict:
    return {
        "id": question.id,
        "text": question.text,
        "correct_option": question.correct_option,
    }


def _options_payload(question: Question) -> dict:
    return {
        "A": question.option_a,
        "B": question.option_b,
        "C": question.option_c,
        "D": question.option_d,
    }


async def get_active_session_id() -> int | None:
    value = await redis_client.get(ACTIVE_SESSION_KEY)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def compute_tally(session_id: int) -> dict:
    votes = await redis_client.hgetall(votes_key(session_id))
    roster = await redis_client.smembers(roster_key(session_id))

    counts = {"A": 0, "B": 0, "C": 0, "D": 0}

    for option in votes.values():
        if option in counts:
            counts[option] += 1

    voted = sorted(int(student_id) for student_id in votes)
    roster_ids = sorted(int(student_id) for student_id in roster)

    voted_set = set(voted)
    missing = [
        student_id
        for student_id in roster_ids
        if student_id not in voted_set
    ]

    return {
        "session_id": session_id,
        "counts": counts,
        "total": len(voted),
        "voted": voted,
        "missing": missing,
    }

async def build_state_sync() -> dict:
    session_id = await get_active_session_id()

    if session_id is None:
        return {"session_id": None, "status": "closed"}

    async with SessionLocal() as db:
        session = await db.get(VotingSession, session_id)

        if session is None or session.status != "open":
            await cleanup_stale_active_session()
            return {"session_id": None, "status": "closed"}

        question = await db.get(Question, session.question_id)

        if question is None:
            return {"session_id": None, "status": "closed"}

        roster = sorted(
            int(student_id)
            for student_id in await redis_client.smembers(
                roster_key(session_id)
            )
        )

        tally = await compute_tally(session_id)

        return {
            "session_id": session_id,
            "status": session.status,
            "question": _question_payload(question),
            "options": _options_payload(question),
            "roster": roster,
            "counts": tally["counts"],
            "total": tally["total"],
            "voted": tally["voted"],
            "missing": tally["missing"],
        }


def _student_closed_state() -> dict:
    """Estado mínimo que recibe un estudiante cuando no hay votación."""

    return {
        "session_id": None,
        "status": "closed",
        "voting_status": "closed",
        "question": None,
        "options": None,
        "your_vote": None,
    }


async def build_student_state(student_id: int) -> dict:
    """Estado de la votación visible para un estudiante.

    No incluye el roster, los votos de los demás ni los conteos: mientras la
    votación está abierta el alumno solo debe ver la pregunta y sus opciones.
    """

    session_id = await get_active_session_id()

    if session_id is None:
        return _student_closed_state()

    async with SessionLocal() as db:
        session = await db.get(VotingSession, session_id)

        if session is None or session.status != "open":
            await cleanup_stale_active_session()
            return _student_closed_state()

        question = await db.get(Question, session.question_id)

        if question is None:
            return _student_closed_state()

        payload = {
            "session_id": session_id,
            "status": "open",
            "voting_status": "open",
            "question": {
                "id": question.id,
                "text": question.text,
            },
            "options": _options_payload(question),
            "your_vote": await redis_client.hget(
                votes_key(session_id), str(student_id)
            ),
        }

    return payload


async def _resolve_student_id(reference) -> int | None:
    """Resuelve un estudiante por su token QR o por su aruco_id."""

    value = str(reference or "").strip()

    if not value:
        return None

    async with SessionLocal() as db:
        result = await db.execute(
            select(Student).where(Student.qr_token == value)
        )
        student = result.scalar_one_or_none()

        if student is not None:
            return student.id

        if value.isdigit():
            result = await db.execute(
                select(Student).where(Student.aruco_id == int(value))
            )
            student = result.scalar_one_or_none()

            if student is not None:
                return student.id

    return None


def student_open_payload(evento: dict) -> dict:
    """Versión saneada de `vote:open` para los estudiantes.

    Se elimina el roster y cualquier dato del resto del curso: el alumno
    solo necesita saber qué pregunta está abierta y con qué opciones.
    """

    question = evento.get("question") or {}

    return {
        "session_id": evento.get("session_id"),
        "status": "open",
        "voting_status": "open",
        "question": {
            "id": question.get("id"),
            "text": question.get("text"),
        },
        "options": evento.get("options") or {},
    }


def student_results_payload(results: dict, student_id: int | None) -> dict:
    """Resultado final sin datos de otros alumnos.

    Si se conoce el estudiante se agrega su propia respuesta; nunca se
    incluye `per_student`, que contiene nombres y votos de todo el curso.
    """

    payload = {
        "session_id": results.get("session_id"),
        "counts": results.get("counts") or {},
        "correct_option": results.get("correct_option"),
        "status": "closed",
        "voting_status": "closed",
    }

    if student_id is None:
        return payload

    fila = next(
        (
            item
            for item in results.get("per_student") or []
            if item.get("student_id") == student_id
        ),
        None,
    )

    payload["your"] = {
        "option": fila.get("option") if fila else None,
        "correct": fila.get("correct") if fila else None,
    }

    return payload


async def list_student_ids() -> list[int]:
    """Ids de los estudiantes con cuenta, para avisos personalizados."""

    async with SessionLocal() as db:
        result = await db.execute(select(Student.id).order_by(Student.id))
        return list(result.scalars().all())


async def open_session(question_id: int) -> tuple[int, dict]:
    async with SessionLocal() as db:
        question = await db.get(Question, question_id)

        if question is None:
            raise ValueError("question_not_found")

        abierta = (
            await db.execute(
                select(VotingSession).where(
                    VotingSession.status == "open"
                )
            )
        ).scalars().first()

        if abierta is not None:
            raise ValueError("session_already_open")

        result = await db.execute(
            select(VotingSession)
            .where(VotingSession.question_id == question_id)
            .order_by(VotingSession.id.desc())
            .limit(1)
        )

        session = result.scalar_one_or_none()

        if session is not None:
            session.status = "open"
            session.closed_at = None

            await db.flush()
            session_id = session.id

            roster = sorted(
                (
                    await db.execute(select(Student.id))
                ).scalars().all()
            )

            vote_result = await db.execute(
                select(Student.id, Vote.option)
                .join(Vote, Vote.student_id == Student.id)
                .where(Vote.session_id == session_id)
            )

            votos_guardados = {
                str(student_id): option
                for student_id, option in vote_result.all()
            }

        else:
            session = VotingSession(
                question_id=question_id,
                status="open",
            )

            db.add(session)
            await db.flush()

            session_id = session.id

            roster = sorted(
                (
                    await db.execute(select(Student.id))
                ).scalars().all()
            )

            votos_guardados = {}

        payload = {
            "session_id": session_id,
            "question": _question_payload(question),
            "options": _options_payload(question),
            "roster": roster,
        }

        await db.commit()

    pipe = redis_client.pipeline()

    pipe.delete(
        votes_key(session_id),
        roster_key(session_id),
        counts_key(session_id),
    )

    pipe.set(ACTIVE_SESSION_KEY, session_id)

    if roster:
        pipe.sadd(roster_key(session_id), *roster)

    if votos_guardados:
        pipe.hset(
            votes_key(session_id),
            mapping=votos_guardados,
        )

    await pipe.execute()

    return session_id, payload

async def _results_from_db(
    db, session: VotingSession, question: Question | None
) -> dict:
    filas = (
        await db.execute(
            select(Vote.student_id, Student.name, Vote.option)
            .join(Student, Student.id == Vote.student_id)
            .where(Vote.session_id == session.id)
            .order_by(Student.name)
        )
    ).all()

    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    per_student = []
    correct_option = question.correct_option if question is not None else None

    for student_id, name, option in filas:
        if option in counts:
            counts[option] += 1
        per_student.append(
            {
                "student_id": student_id,
                "name": name,
                "option": option,
                "correct": option == correct_option,
            }
        )

    return {
        "session_id": session.id,
        "counts": counts,
        "correct_option": correct_option,
        "per_student": per_student,
    }


async def close_session(session_id: int) -> dict:
    async with SessionLocal() as db:
        session = await db.get(VotingSession, session_id)

        if session is None:
            raise LookupError("session_not_found")

        question = await db.get(Question, session.question_id)

        if session.status == "closed":
            results = await _results_from_db(db, session, question)

        else:
            votes = await redis_client.hgetall(votes_key(session_id))

            students = {
                student.id: student
                for student in (
                    await db.execute(select(Student))
                ).scalars().all()
            }

            filas = []

            for student_id_str, option in votes.items():
                try:
                    student_id = int(student_id_str)
                except (TypeError, ValueError):
                    continue

                student = students.get(student_id)

                if student is None or option not in VALID_OPTIONS:
                    continue

                filas.append({
                    "session_id": session_id,
                    "student_id": student.id,
                    "option": option,
                })

            if filas:
                stmt = pg_insert(Vote).values(filas)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["session_id", "student_id"],
                    set_={"option": stmt.excluded.option},
                )
                await db.execute(stmt)

            session.status = "closed"
            session.closed_at = datetime.now(timezone.utc)

            await db.commit()

            results = await _results_from_db(db, session, question)

    await _cleanup_redis(session_id)

    return results

async def get_results(session_id: int) -> dict:
    async with SessionLocal() as db:
        session = await db.get(VotingSession, session_id)
        if session is None:
            raise LookupError("session_not_found")
        question = await db.get(Question, session.question_id)
        return await _results_from_db(db, session, question)

async def get_latest_question_results(question_id: int):
    async with SessionLocal() as db:
        question = await db.get(Question, question_id)

        if question is None:
            raise LookupError("question_not_found")

        result = await db.execute(
            select(VotingSession)
            .where(VotingSession.question_id == question_id)
            .order_by(VotingSession.id.desc())
            .limit(1)
        )

        voting_session = result.scalar_one_or_none()

        if voting_session is None:
            return None

        return await _results_from_db(
            db,
            voting_session,
            question
        )


async def cast_vote(session_id: int, student_ref, option: str):
    """Registra un voto y devuelve (ok, motivo, tally, student_id).

    El identificador puede ser el token QR permanente del estudiante o su
    aruco_id numérico (compatibilidad con el módulo local antiguo).
    """

    active_session = await redis_client.get(ACTIVE_SESSION_KEY)

    if active_session is None:
        return False, "closed", None, None

    try:
        active_id = int(active_session)
    except (TypeError, ValueError):
        return False, "closed", None, None

    if active_id != session_id:
        return False, "stale_session", None, None

    student_id = await _resolve_student_id(student_ref)

    if student_id is None:
        return False, "unknown", None, None

    is_member = await redis_client.sismember(
        roster_key(session_id),
        str(student_id),
    )

    if not is_member:
        return False, "unknown", None, None

    option = str(option or "").upper()

    if option not in VALID_OPTIONS:
        return False, "invalid", None, None

    async with SessionLocal() as db:
        voting_session = await db.get(VotingSession, session_id)

        if voting_session is None or voting_session.status != "open":
            return False, "closed", None, None

        stmt = pg_insert(Vote).values(
            session_id=session_id,
            student_id=student_id,
            option=option,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["session_id", "student_id"],
            set_={"option": option},
        )

        await db.execute(stmt)
        await db.commit()

    await redis_client.hset(
        votes_key(session_id),
        str(student_id),
        option,
    )

    tally = await compute_tally(session_id)

    return True, None, tally, student_id

async def _cleanup_redis(session_id: int) -> None:
    active = await redis_client.get(ACTIVE_SESSION_KEY)
    pipe = redis_client.pipeline()
    pipe.delete(votes_key(session_id), roster_key(session_id), counts_key(session_id))
    if active is not None:
        try:
            if int(active) == session_id:
                pipe.delete(ACTIVE_SESSION_KEY)
        except (TypeError, ValueError):
            pipe.delete(ACTIVE_SESSION_KEY)
    await pipe.execute()


async def cleanup_stale_active_session() -> None:
    active = await get_active_session_id()
    if active is None:
        return

    async with SessionLocal() as db:
        session = await db.get(VotingSession, active)
        if session is not None and session.status == "open":
            return

    await redis_client.delete(
        ACTIVE_SESSION_KEY,
        votes_key(active),
        roster_key(active),
        counts_key(active),
    )

async def clear_question_answers(question_id: int) -> dict:
    active_session_id = await get_active_session_id()

    async with SessionLocal() as db:
        question = await db.get(Question, question_id)

        if question is None:
            raise LookupError("question_not_found")

        # Buscar todas las sesiones asociadas a esta pregunta.
        result = await db.execute(
            select(VotingSession.id).where(
                VotingSession.question_id == question_id
            )
        )

        session_ids = list(result.scalars().all())

        # Eliminar todas las respuestas guardadas en PostgreSQL.
        if session_ids:
            deletion = await db.execute(
                delete(Vote).where(
                    Vote.session_id.in_(session_ids)
                )
            )
            deleted_votes = deletion.rowcount or 0
        else:
            deleted_votes = 0

        # Comprobar si esta pregunta tiene una sesión abierta.
        active_session = None

        if active_session_id is not None:
            active_session = await db.get(
                VotingSession,
                active_session_id
            )

            if (
                active_session is None
                or active_session.question_id != question_id
                or active_session.status != "open"
            ):
                active_session = None

        await db.commit()

    tally = None

    # Si está abierta, limpiar sus votos temporales sin cerrar la sesión.
    if active_session is not None:
        await redis_client.delete(
            votes_key(active_session_id),
            counts_key(active_session_id)
        )

        tally = await compute_tally(active_session_id)

    return {
        "question_id": question_id,
        "deleted_votes": deleted_votes,
        "session_id": active_session_id if active_session else None,
        "tally": tally
    }

async def remove_student(student_id: int) -> dict:
    active_session_id = await get_active_session_id()
    active_session = None

    async with SessionLocal() as db:
        student = await db.get(Student, student_id)

        if student is None:
            raise LookupError("student_not_found")

        await db.execute(
            delete(Vote).where(Vote.student_id == student_id)
        )

        await db.delete(student)

        if active_session_id is not None:
            active_session = await db.get(
                VotingSession,
                active_session_id,
            )

            if (
                active_session is None
                or active_session.status != "open"
            ):
                active_session = None

        await db.commit()

    tally = None

    if active_session is not None:
        await redis_client.srem(
            roster_key(active_session_id),
            str(student_id),
        )

        await redis_client.hdel(
            votes_key(active_session_id),
            str(student_id),
        )

        tally = await compute_tally(active_session_id)

    return {
        "student_id": student_id,
        "tally": tally,
    }

async def remove_question(question_id: int) -> dict:
    active_session_id = await get_active_session_id()
    session_ids = []
    active_session_deleted = False

    async with SessionLocal() as db:
        question = await db.get(Question, question_id)

        if question is None:
            raise LookupError("question_not_found")

        # Buscar todas las sesiones de esta pregunta.
        result = await db.execute(
            select(VotingSession.id).where(
                VotingSession.question_id == question_id
            )
        )
        session_ids = list(result.scalars().all())

        # Comprobar si la sesión activa pertenece a esta pregunta.
        if active_session_id is not None:
            active_session = await db.get(
                VotingSession, active_session_id
            )

            if (
                active_session is not None
                and active_session.question_id == question_id
            ):
                active_session_deleted = True

        # Primero eliminar las respuestas.
        if session_ids:
            await db.execute(
                delete(Vote).where(
                    Vote.session_id.in_(session_ids)
                )
            )

            # Después eliminar las sesiones.
            await db.execute(
                delete(VotingSession).where(
                    VotingSession.id.in_(session_ids)
                )
            )

        # Finalmente eliminar la pregunta.
        await db.delete(question)

        await db.commit()

    # Limpiar los datos de todas las sesiones en Redis.
    for session_id in session_ids:
        await _cleanup_redis(session_id)

    return {
        "question_id": question_id,
        "deleted_sessions": len(session_ids),
        "active_session_deleted": active_session_deleted,
        "active_session_id": (
            active_session_id if active_session_deleted else None
        )
    }