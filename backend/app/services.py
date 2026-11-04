from datetime import datetime, timezone

from sqlalchemy import select
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

    voted = sorted(int(aruco_id) for aruco_id in votes)
    roster_ids = sorted(int(aruco_id) for aruco_id in roster)
    voted_set = set(voted)
    missing = [aruco_id for aruco_id in roster_ids if aruco_id not in voted_set]

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
            int(aruco_id)
            for aruco_id in await redis_client.smembers(roster_key(session_id))
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


async def open_session(question_id: int) -> tuple[int, dict]:
    async with SessionLocal() as db:
        question = await db.get(Question, question_id)
        if question is None:
            raise ValueError("question_not_found")

        abierta = (
            await db.execute(
                select(VotingSession).where(VotingSession.status == "open")
            )
        ).scalars().first()
        if abierta is not None:
            raise ValueError("session_already_open")

        session = VotingSession(question_id=question_id, status="open")
        db.add(session)
        await db.flush()

        roster = sorted(
            (await db.execute(select(Student.aruco_id))).scalars().all()
        )
        session_id = session.id
        payload = {
            "session_id": session_id,
            "question": _question_payload(question),
            "options": _options_payload(question),
            "roster": roster,
        }
        await db.commit()

    await redis_client.set(ACTIVE_SESSION_KEY, session_id)
    if roster:
        await redis_client.sadd(roster_key(session_id), *roster)

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
                student.aruco_id: student
                for student in (
                    await db.execute(select(Student))
                ).scalars().all()
            }

            filas = []
            for aruco_str, option in votes.items():
                try:
                    aruco_id = int(aruco_str)
                except (TypeError, ValueError):
                    continue
                student = students.get(aruco_id)
                if student is None or option not in VALID_OPTIONS:
                    continue
                filas.append(
                    {
                        "session_id": session_id,
                        "student_id": student.id,
                        "option": option,
                    }
                )

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


async def cast_vote(
    session_id: int, aruco_id: int, option: str
) -> tuple[bool, str | None, dict | None]:
    active = await get_active_session_id()
    if active is None:
        return False, "closed", None
    if session_id != active:
        return False, "stale_session", None

    if not await redis_client.sismember(roster_key(session_id), aruco_id):
        return False, "unknown", None

    option = (option or "").upper()
    if option not in VALID_OPTIONS:
        return False, "invalid", None

    await redis_client.hset(votes_key(session_id), str(aruco_id), option)
    tally = await compute_tally(session_id)
    return True, None, tally


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
