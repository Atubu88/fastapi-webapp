from typing import Optional

from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from core.config import TEMPLATES_DIR
from core.models import Quiz, Question, Option
from core.database import get_session
import re


def _format_question_label(count: int) -> str:
    """Вернуть строку с количеством вопросов и корректным склонением."""
    remainder_10 = count % 10
    remainder_100 = count % 100

    if remainder_10 == 1 and remainder_100 != 11:
        suffix = "вопрос"
    elif 2 <= remainder_10 <= 4 and not 12 <= remainder_100 <= 14:
        suffix = "вопроса"
    else:
        suffix = "вопросов"

    return f"{count} {suffix}"


def _render_add_quiz_page(
    request: Request,
    session: Session,
    message: Optional[str] = None,
    message_type: str = "info",
):
    quizzes = session.query(Quiz).order_by(Quiz.id.desc()).all()
    quiz_cards = []

    for quiz in quizzes:
        description = (quiz.description or "").strip()
        first_line = description.splitlines()[0] if description else "Описание отсутствует"
        preview = first_line if len(first_line) <= 120 else first_line[:117] + "..."

        quiz_cards.append(
            {
                "id": quiz.id,
                "title": quiz.title,
                "question_label": _format_question_label(len(quiz.questions)),
                "preview": preview,
            }
        )

    return templates.TemplateResponse(
        "admin/add_quiz.html",
        {
            "request": request,
            "message": message,
            "message_type": message_type,
            "quizzes": quiz_cards,
        },
    )

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/", response_class=HTMLResponse)
async def admin_root(request: Request):
    return templates.TemplateResponse("admin/menu.html", {"request": request})


@router.get("/add_quiz", response_class=HTMLResponse)
async def get_add_quiz(request: Request, session: Session = Depends(get_session)):
    return _render_add_quiz_page(request, session)


@router.post("/add_quiz", response_class=HTMLResponse)
async def post_add_quiz(
    request: Request,
    content: str = Form(...),
    session: Session = Depends(get_session),
):
    if not content.strip():
        return _render_add_quiz_page(
            request,
            session,
            message="❌ Вставь текст викторины!",
            message_type="error",
        )

    # Извлекаем тему
    first_line = content.strip().splitlines()[0]
    match = re.search(r"^Тема:\s*(.+)", first_line)
    title = match.group(1).strip() if match else "Без темы"

    # Создаём викторину
    quiz = Quiz(title=title, description=content.strip())
    session.add(quiz)
    session.commit()
    session.refresh(quiz)

    # Парсим вопросы
    question_blocks = re.split(r"\n\d+\.\s", content.strip())[1:]  # разбиваем по номерам
    question_titles = re.findall(r"\n\d+\.\s(.*?)\n-", content.strip(), re.DOTALL)

    for q_index, block in enumerate(question_blocks):
        question_text = question_titles[q_index].strip() if q_index < len(question_titles) else "Без текста"
        explanation_match = re.search(r"Пояснение:\s*(.+)", block)
        explanation = explanation_match.group(1).strip() if explanation_match else None

        # Создаём вопрос
        question = Question(
            text=question_text,
            explanation=explanation,
            quiz_id=quiz.id
        )
        session.add(question)
        session.commit()
        session.refresh(question)

        # Извлекаем варианты ответов
        options = re.findall(r"-\s*(.+)", block)
        correct_match = re.search(r"Ответ:\s*(\d+)", block)
        correct_index = int(correct_match.group(1)) - 1 if correct_match else None

        for i, option_text in enumerate(options):
            option = Option(
                text=option_text.strip(),
                is_correct=(i == correct_index),
                question_id=question.id
            )
            session.add(option)

    session.commit()

    return _render_add_quiz_page(
        request,
        session,
        message=f"✅ Викторина «{title}» успешно добавлена вместе с {len(question_blocks)} вопросами!",
        message_type="success",
    )


@router.post("/quizzes/{quiz_id}/delete", response_class=HTMLResponse)
async def delete_quiz(
    request: Request,
    quiz_id: int,
    session: Session = Depends(get_session),
):
    quiz = session.get(Quiz, quiz_id)

    if quiz is None:
        return _render_add_quiz_page(
            request,
            session,
            message="⚠️ Викторина не найдена или уже удалена.",
            message_type="error",
        )

    title = quiz.title
    session.delete(quiz)
    session.commit()

    return _render_add_quiz_page(
        request,
        session,
        message=f"🗑️ Викторина «{title}» удалена.",
        message_type="success",
    )