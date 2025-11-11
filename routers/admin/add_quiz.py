from fastapi import APIRouter, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from core.config import TEMPLATES_DIR
from core.models import Quiz, Question, Option
from core.database import get_session
import re

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/", response_class=HTMLResponse)
async def admin_root(request: Request):
    return templates.TemplateResponse("admin/menu.html", {"request": request})


@router.get("/add_quiz", response_class=HTMLResponse)
async def get_add_quiz(request: Request):
    return templates.TemplateResponse("admin/add_quiz.html", {"request": request, "message": None})


@router.post("/add_quiz", response_class=HTMLResponse)
async def post_add_quiz(
    request: Request,
    content: str = Form(...),
    session: Session = Depends(get_session),
):
    if not content.strip():
        return templates.TemplateResponse(
            "admin/add_quiz.html",
            {"request": request, "message": "❌ Вставь текст викторины!"}
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

    return templates.TemplateResponse(
        "admin/add_quiz.html",
        {
            "request": request,
            "message": f"✅ Викторина «{title}» успешно добавлена вместе с {len(question_blocks)} вопросами!"
        }
    )
