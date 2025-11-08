from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import asc, delete, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from webapp.db.models import Option, Question, Quiz, Team, TeamMember, TeamResult, User
from webapp.db.session import run_in_session_async


LOGGER = logging.getLogger(__name__)


def _to_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise ValueError(f"Cannot convert {value!r} to UUID")


def _to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value))


def _iso_or_none(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.isoformat()


def _serialize_user(user: User) -> Dict[str, Any]:
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def _serialize_team(team: Team) -> Dict[str, Any]:
    return {
        "id": str(team.id) if team.id is not None else None,
        "name": team.name,
        "code": team.code,
        "captain_id": team.captain_id,
        "created_at": _iso_or_none(team.created_at),
        "start_time": _iso_or_none(team.start_time),
        "match_id": team.match_id,
        "ready": bool(team.ready) if team.ready is not None else False,
        "quiz_id": team.quiz_id,
    }


def _serialize_team_member(member: TeamMember) -> Dict[str, Any]:
    return {
        "id": str(member.id) if member.id is not None else None,
        "team_id": str(member.team_id) if member.team_id is not None else None,
        "user_id": member.user_id,
        "is_captain": bool(member.is_captain),
        "joined_at": _iso_or_none(member.joined_at),
    }


def _serialize_team_result(result: TeamResult) -> Dict[str, Any]:
    return {
        "id": str(result.id) if result.id is not None else None,
        "team_id": str(result.team_id) if result.team_id is not None else None,
        "quiz_id": result.quiz_id,
        "score": result.score,
        "time_taken": result.time_taken,
        "created_at": _iso_or_none(result.created_at),
    }


def _serialize_option(option: Option) -> Dict[str, Any]:
    return {
        "id": option.id,
        "question_id": option.question_id,
        "text": option.text,
        "is_correct": option.is_correct,
    }


def _serialize_question(question: Question) -> Dict[str, Any]:
    return {
        "id": question.id,
        "quiz_id": question.quiz_id,
        "text": question.text,
        "explanation": question.explanation,
        "options": [_serialize_option(option) for option in (question.options or [])],
    }


def _serialize_quiz(quiz: Quiz, *, include_questions: bool = True) -> Dict[str, Any]:
    payload = {
        "id": quiz.id,
        "title": quiz.title,
        "description": quiz.description,
        "is_active": quiz.is_active,
        "category_id": quiz.category_id,
    }
    if include_questions:
        payload["questions"] = [_serialize_question(question) for question in quiz.questions or []]
    return payload


def _parse_filters(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    if not params:
        return filters
    for key, raw_value in params.items():
        if key in {"select", "order", "limit"}:
            continue
        if isinstance(raw_value, str):
            if raw_value.startswith("eq."):
                filters[key] = raw_value[3:]
                continue
            if raw_value.startswith("in.(") and raw_value.endswith(")"):
                content = raw_value[4:-1]
                filters[key] = [item.strip() for item in content.split(",") if item.strip()]
                continue
        filters[key] = raw_value
    return filters


def _apply_select(payload: Dict[str, Any], params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not params or "select" not in params:
        return payload
    select_clause = params["select"]
    if "(" in select_clause:
        return payload
    fields = [field.strip() for field in select_clause.split(",") if field.strip()]
    return {field: payload.get(field) for field in fields}


def _parse_order_clause(order: Optional[str]) -> List[tuple[str, bool]]:
    if not order:
        return []
    clauses: List[tuple[str, bool]] = []
    for part in order.split(","):
        part = part.strip()
        if not part:
            continue
        if "." in part:
            column, direction = part.split(".", 1)
        else:
            column, direction = part, "asc"
        clauses.append((column.strip(), direction.strip().lower() == "desc"))
    return clauses


def _parse_iso_datetime(value: str) -> datetime:
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    dt = datetime.fromisoformat(candidate)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _not_found(path: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Resource not found: {path}")


async def _handle_users(
    method: str,
    params: Optional[Dict[str, Any]],
    json_payload: Optional[Dict[str, Any] | List[Dict[str, Any]]],
) -> Any:
    if method == "GET":
        filters = _parse_filters(params)
        limit = int(params.get("limit")) if params and params.get("limit") else None

        async def query(session):
            stmt = select(User)
            ids = filters.get("id")
            if isinstance(ids, list):
                stmt = stmt.where(User.id.in_([_to_int(item) for item in ids]))
            elif ids is not None:
                stmt = stmt.where(User.id == _to_int(ids))
            if "telegram_id" in filters:
                value = filters["telegram_id"]
                if isinstance(value, list):
                    stmt = stmt.where(User.telegram_id.in_([_to_int(item) for item in value]))
                else:
                    stmt = stmt.where(User.telegram_id == _to_int(value))
            if "username" in filters:
                value = filters["username"]
                if isinstance(value, list):
                    stmt = stmt.where(User.username.in_(value))
                else:
                    stmt = stmt.where(User.username == value)
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_apply_select(_serialize_user(row), params) for row in rows]

        return await run_in_session_async(query)

    if method == "POST":
        if not isinstance(json_payload, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid payload for users")

        async def create(session):
            user = User(
                telegram_id=_to_int(json_payload.get("telegram_id")),
                username=json_payload.get("username"),
                first_name=json_payload.get("first_name"),
                last_name=json_payload.get("last_name"),
            )
            session.add(user)
            try:
                await session.flush()
            except IntegrityError as exc:  # pragma: no cover - defensive
                LOGGER.warning("Failed to insert user: %s", exc)
                raise HTTPException(status.HTTP_409_CONFLICT, detail="User already exists") from exc
            return [_serialize_user(user)]

        return await run_in_session_async(create)

    raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, detail="Unsupported users operation")


async def _handle_teams(
    method: str,
    params: Optional[Dict[str, Any]],
    json_payload: Optional[Dict[str, Any] | List[Dict[str, Any]]],
) -> Any:
    if method == "GET":
        filters = _parse_filters(params)
        limit = int(params.get("limit")) if params and params.get("limit") else None

        async def query(session):
            stmt = select(Team)
            if "id" in filters:
                stmt = stmt.where(Team.id == _to_uuid(filters["id"]))
            if "code" in filters:
                stmt = stmt.where(Team.code == filters["code"])
            if "match_id" in filters:
                stmt = stmt.where(Team.match_id == filters["match_id"])
            if "captain_id" in filters:
                stmt = stmt.where(Team.captain_id == _to_int(filters["captain_id"]))
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [_apply_select(_serialize_team(row), params) for row in rows]

        return await run_in_session_async(query)

    if method == "POST":
        if not isinstance(json_payload, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid team payload")
        required_fields = {"name", "code", "captain_id"}
        missing = [field for field in required_fields if not json_payload.get(field)]
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Missing team fields: {', '.join(missing)}",
            )

        async def create(session):
            team = Team(
                name=json_payload.get("name"),
                code=json_payload.get("code"),
                captain_id=_to_int(json_payload.get("captain_id")),
                match_id=json_payload.get("match_id"),
                ready=bool(json_payload.get("ready")),
                quiz_id=json_payload.get("quiz_id"),
            )
            session.add(team)
            await session.flush()
            return [_serialize_team(team)]

        return await run_in_session_async(create)

    if method == "PATCH":
        filters = _parse_filters(params)
        if "id" not in filters:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Team id filter required")
        if not isinstance(json_payload, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid team update payload")

        async def update_team(session):
            team_id = _to_uuid(filters["id"])
            stmt = select(Team).where(Team.id == team_id)
            team = (await session.execute(stmt)).scalars().one_or_none()
            if not team:
                raise _not_found("teams")

            if "name" in json_payload:
                team.name = json_payload["name"]
            if "code" in json_payload:
                team.code = json_payload["code"]
            if "ready" in json_payload:
                team.ready = bool(json_payload["ready"])
            if "quiz_id" in json_payload:
                team.quiz_id = json_payload["quiz_id"]
            if "start_time" in json_payload and json_payload["start_time"]:
                try:
                    team.start_time = _parse_iso_datetime(str(json_payload["start_time"]))
                except ValueError as exc:
                    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid start_time") from exc
            await session.flush()
            return [_serialize_team(team)]

        return await run_in_session_async(update_team)

    if method == "DELETE":
        filters = _parse_filters(params)
        if not filters:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Deletion filter required")

        async def delete_team(session):
            stmt = delete(Team)
            if "id" in filters:
                stmt = stmt.where(Team.id == _to_uuid(filters["id"]))
            if "code" in filters:
                stmt = stmt.where(Team.code == filters["code"])
            if "match_id" in filters:
                stmt = stmt.where(Team.match_id == filters["match_id"])
            await session.execute(stmt)
            return None

        return await run_in_session_async(delete_team)

    raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, detail="Unsupported teams operation")


async def _handle_team_members(
    method: str,
    params: Optional[Dict[str, Any]],
    json_payload: Optional[Dict[str, Any] | List[Dict[str, Any]]],
) -> Any:
    if method == "GET":
        filters = _parse_filters(params)

        async def query(session):
            stmt = select(TeamMember)
            if "team_id" in filters:
                stmt = stmt.where(TeamMember.team_id == _to_uuid(filters["team_id"]))
            if "user_id" in filters:
                stmt = stmt.where(TeamMember.user_id == _to_int(filters["user_id"]))
            stmt = stmt.order_by(asc(TeamMember.joined_at))
            members = (await session.execute(stmt)).scalars().all()
            return [_apply_select(_serialize_team_member(member), params) for member in members]

        return await run_in_session_async(query)

    if method == "POST":
        if not isinstance(json_payload, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid team member payload")
        if not json_payload.get("team_id") or not json_payload.get("user_id"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="team_id and user_id are required")

        async def create(session):
            member = TeamMember(
                team_id=_to_uuid(json_payload.get("team_id")),
                user_id=_to_int(json_payload.get("user_id")),
                is_captain=bool(json_payload.get("is_captain")),
            )
            session.add(member)
            await session.flush()
            return [_serialize_team_member(member)]

        return await run_in_session_async(create)

    if method == "DELETE":
        filters = _parse_filters(params)
        if not filters:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Deletion filter required")

        async def remove(session):
            stmt = delete(TeamMember)
            if "team_id" in filters:
                stmt = stmt.where(TeamMember.team_id == _to_uuid(filters["team_id"]))
            if "user_id" in filters:
                stmt = stmt.where(TeamMember.user_id == _to_int(filters["user_id"]))
            await session.execute(stmt)
            return None

        return await run_in_session_async(remove)

    raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, detail="Unsupported team_members operation")


async def _handle_team_results(
    method: str,
    params: Optional[Dict[str, Any]],
    json_payload: Optional[Dict[str, Any] | List[Dict[str, Any]]],
) -> Any:
    if method == "GET":
        filters = _parse_filters(params)
        order_clause = _parse_order_clause(params.get("order") if params else None)

        async def query(session):
            stmt = select(TeamResult)
            if "quiz_id" in filters:
                stmt = stmt.where(TeamResult.quiz_id == _to_int(filters["quiz_id"]))
            if "team_id" in filters:
                stmt = stmt.where(TeamResult.team_id == _to_uuid(filters["team_id"]))
            for column, desc_flag in order_clause:
                column_attr = getattr(TeamResult, column, None)
                if column_attr is None:
                    continue
                stmt = stmt.order_by(desc(column_attr) if desc_flag else asc(column_attr))
            results = (await session.execute(stmt)).scalars().all()
            return [_apply_select(_serialize_team_result(result), params) for result in results]

        return await run_in_session_async(query)

    if method == "POST":
        if not isinstance(json_payload, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid team result payload")
        if not json_payload.get("team_id") or json_payload.get("quiz_id") in (None, ""):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="team_id and quiz_id are required")

        async def create(session):
            result = TeamResult(
                team_id=_to_uuid(json_payload.get("team_id")),
                quiz_id=_to_int(json_payload.get("quiz_id")),
                score=_to_int(json_payload.get("score", 0)),
                time_taken=float(json_payload.get("time_taken")) if json_payload.get("time_taken") is not None else None,
            )
            session.add(result)
            await session.flush()
            return [_serialize_team_result(result)]

        return await run_in_session_async(create)

    if method == "PATCH":
        filters = _parse_filters(params)
        if "id" not in filters:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Team result id required")
        if not isinstance(json_payload, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid team result payload")

        async def update_result(session):
            result_id = _to_uuid(filters["id"])
            stmt = select(TeamResult).where(TeamResult.id == result_id)
            result = (await session.execute(stmt)).scalars().one_or_none()
            if not result:
                raise _not_found("team_results")
            if "score" in json_payload:
                result.score = _to_int(json_payload["score"])
            if "time_taken" in json_payload:
                value = json_payload["time_taken"]
                result.time_taken = float(value) if value is not None else None
            await session.flush()
            return [_serialize_team_result(result)]

        return await run_in_session_async(update_result)

    raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, detail="Unsupported team_results operation")


async def _handle_quizzes(
    method: str,
    params: Optional[Dict[str, Any]],
    json_payload: Optional[Dict[str, Any] | List[Dict[str, Any]]],
) -> Any:
    if method != "GET":
        raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, detail="Unsupported quizzes operation")

    filters = _parse_filters(params)
    limit = int(params.get("limit")) if params and params.get("limit") else None
    include_questions = True
    select_clause = params.get("select") if params else None
    if select_clause and "questions" not in select_clause:
        include_questions = False

    async def query(session):
        stmt = select(Quiz)
        if include_questions:
            stmt = stmt.options(selectinload(Quiz.questions).selectinload(Question.options))
        if "id" in filters:
            stmt = stmt.where(Quiz.id == _to_int(filters["id"]))
        if "is_active" in filters:
            value = filters["is_active"].lower() in {"true", "eq.true"}
            stmt = stmt.where(Quiz.is_active.is_(value))
        if params and params.get("order"):
            order_clause = _parse_order_clause(params.get("order"))
            for column, desc_flag in order_clause:
                column_attr = getattr(Quiz, column, None)
                if column_attr is None:
                    continue
                stmt = stmt.order_by(desc(column_attr) if desc_flag else asc(column_attr))
        if limit is not None:
            stmt = stmt.limit(limit)
        quizzes = (await session.execute(stmt)).scalars().all()
        response: List[Dict[str, Any]] = []
        for quiz in quizzes:
            payload = _serialize_quiz(quiz, include_questions=include_questions)
            response.append(_apply_select(payload, params))
        return response

    return await run_in_session_async(query)


async def _supabase_request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_payload: Optional[Dict[str, Any] | List[Dict[str, Any]]] = None,
    prefer: Optional[str] = None,
) -> Any:
    resource = path.lower()
    if resource == "users":
        return await _handle_users(method.upper(), params, json_payload)
    if resource == "teams":
        return await _handle_teams(method.upper(), params, json_payload)
    if resource == "team_members":
        return await _handle_team_members(method.upper(), params, json_payload)
    if resource == "team_results":
        return await _handle_team_results(method.upper(), params, json_payload)
    if resource == "quizzes":
        return await _handle_quizzes(method.upper(), params, json_payload)

    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unsupported resource: {path}")


async def _fetch_single_record(table: str, filters: Dict[str, str], select: str = "*") -> Optional[Dict[str, Any]]:
    params: Dict[str, Any] = {"select": select, **filters, "limit": 1}
    data = await _supabase_request("GET", table, params=params)
    if isinstance(data, list) and data:
        return data[0]
    return None


async def _fetch_quiz_options(select: str = "id,title") -> List[Dict[str, Any]]:
    async def query(session):
        stmt = select(Quiz.id, Quiz.title).order_by(asc(Quiz.title))
        rows = (await session.execute(stmt)).all()
        return [{"id": row.id, "title": row.title} for row in rows]

    return await run_in_session_async(query)


async def _fetch_active_quiz() -> Dict[str, Any]:
    async def query(session):
        stmt = (
            select(Quiz)
            .options(selectinload(Quiz.questions).selectinload(Question.options))
            .where(Quiz.is_active.is_(True))
            .order_by(asc(Quiz.id))
        )
        quiz = (await session.execute(stmt)).scalars().first()
        if not quiz:
            raise _not_found("quizzes")
        return _serialize_quiz(quiz, include_questions=True)

    return await run_in_session_async(query)


__all__ = [
    "_supabase_request",
    "_fetch_single_record",
    "_fetch_active_quiz",
    "_fetch_quiz_options",
]
