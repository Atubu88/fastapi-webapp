"""SQLAlchemy ORM models for the application database."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


metadata = Base.metadata


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String)
    first_name: Mapped[str | None] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String)

    results: Mapped[list["Result"]] = relationship(
        "Result", back_populates="user", cascade="all, delete-orphan"
    )
    team_memberships: Mapped[list["TeamMember"]] = relationship(
        "TeamMember", back_populates="user", cascade="all, delete-orphan"
    )
    captain_of_teams: Mapped[list["Team"]] = relationship(
        "Team", back_populates="captain", cascade="all, delete-orphan"
    )


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    teams: Mapped[list["Team"]] = relationship(
        "Team", back_populates="match", passive_deletes=True
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    captain_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    match_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True
    )
    ready: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    quiz_id: Mapped[str | None] = mapped_column(Text)

    captain: Mapped[User] = relationship(
        "User", back_populates="captain_of_teams", foreign_keys=[captain_id]
    )
    members: Mapped[list["TeamMember"]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    results: Mapped[list["TeamResult"]] = relationship(
        "TeamResult", back_populates="team", cascade="all, delete-orphan"
    )
    match: Mapped[Match | None] = relationship(
        "Match", back_populates="teams", foreign_keys=[match_id]
    )


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE")
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE")
    )
    is_captain: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    team: Mapped[Team | None] = relationship("Team", back_populates="members")
    user: Mapped[User | None] = relationship(
        "User", back_populates="team_memberships", foreign_keys=[user_id]
    )


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool | None] = mapped_column(Boolean, server_default=text("true"))
    category_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("categories.id", ondelete="SET NULL"))

    category: Mapped["Category" | None] = relationship(
        "Category", back_populates="quizzes"
    )
    questions: Mapped[list["Question"]] = relationship(
        "Question", back_populates="quiz", cascade="all, delete-orphan"
    )
    results: Mapped[list["Result"]] = relationship(
        "Result", back_populates="quiz", cascade="all, delete-orphan"
    )
    team_results: Mapped[list["TeamResult"]] = relationship(
        "TeamResult", back_populates="quiz", cascade="all, delete-orphan"
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    description: Mapped[str | None] = mapped_column(Text)

    quizzes: Mapped[list[Quiz]] = relationship("Quiz", back_populates="category")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    quiz_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"))

    quiz: Mapped[Quiz | None] = relationship("Quiz", back_populates="questions")
    options: Mapped[list["Option"]] = relationship(
        "Option", back_populates="question", cascade="all, delete-orphan"
    )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    question_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("questions.id", ondelete="CASCADE")
    )

    question: Mapped[Question | None] = relationship("Question", back_populates="options")


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    quiz_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("quizzes.id", ondelete="SET NULL"))
    score: Mapped[int | None] = mapped_column(Integer)
    time_taken: Mapped[float | None] = mapped_column(Float)
    date_taken: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), server_default=func.now())

    user: Mapped[User | None] = relationship("User", back_populates="results")
    quiz: Mapped[Quiz | None] = relationship("Quiz", back_populates="results")


class TeamResult(Base):
    __tablename__ = "team_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE")
    )
    quiz_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("quizzes.id", ondelete="SET NULL"))
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    time_taken: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    team: Mapped[Team | None] = relationship("Team", back_populates="results")
    quiz: Mapped[Quiz | None] = relationship("Quiz", back_populates="team_results")


__all__ = (
    "Base",
    "metadata",
    "User",
    "Match",
    "Team",
    "TeamMember",
    "Quiz",
    "Category",
    "Question",
    "Option",
    "Result",
    "TeamResult",
)
