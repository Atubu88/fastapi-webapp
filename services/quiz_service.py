from __future__ import annotations

from string import ascii_uppercase
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.database import get_session
from core.models import Question, Quiz


def _ensure_session(session: Session | None) -> tuple[Session, bool]:
    if session is not None:
        return session, False
    return get_session(), True


def list_quizzes(session: Session | None = None) -> List[dict]:
    db, should_close = _ensure_session(session)
    try:
        stmt = select(Quiz.id, Quiz.title).order_by(Quiz.title)
        rows = db.execute(stmt).all()
        return [
            {"id": row.id, "title": row.title}
            for row in rows
        ]
    finally:
        if should_close:
            db.close()


def get_quiz_details(quiz_id: int, session: Session | None = None) -> Optional[dict]:
    db, should_close = _ensure_session(session)
    try:
        stmt = select(Quiz).where(Quiz.id == quiz_id)
        quiz = db.execute(stmt).scalar_one_or_none()
        if quiz is None:
            return None
        return {
            "id": quiz.id,
            "title": quiz.title,
            "description": quiz.description,
        }
    finally:
        if should_close:
            db.close()


def get_quiz_questions(quiz_id: int, session: Session | None = None) -> List[dict]:
    db, should_close = _ensure_session(session)
    try:
        stmt = (
            select(Question)
            .where(Question.quiz_id == quiz_id)
            .options(selectinload(Question.options))
            .order_by(Question.id)
        )
        questions: Iterable[Question] = db.execute(stmt).scalars().all()
        return [_serialize_question(question) for question in questions]
    finally:
        if should_close:
            db.close()


def _serialize_question(question: Question) -> dict:
    options_payload: List[dict] = []
    correct_option: Optional[str] = None

    for index, option in enumerate(question.options or []):
        option_id = ascii_uppercase[index % len(ascii_uppercase)]
        options_payload.append({"id": option_id, "text": option.text})
        if option.is_correct:
            correct_option = option_id

    payload = {
        "id": question.id,
        "text": question.text,
        "description": question.explanation,
        "options": options_payload,
        "correct_option": correct_option,
        "score": 1,
    }
    return payload


__all__ = [
    "get_quiz_details",
    "get_quiz_questions",
    "list_quizzes",
]
