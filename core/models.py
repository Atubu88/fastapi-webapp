from __future__ import annotations

from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    questions: Mapped[List["Question"]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quiz_id: Mapped[Optional[int]] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"))

    quiz: Mapped[Optional[Quiz]] = relationship(back_populates="questions")
    options: Mapped[List["Option"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Option.id",
    )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    question_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=True,
    )

    question: Mapped[Optional[Question]] = relationship(back_populates="options")


__all__ = ["Base", "Quiz", "Question", "Option"]
