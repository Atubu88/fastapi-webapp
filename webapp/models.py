"""SQLAlchemy ORM models for the FastAPI web application database.

These models are scoped exclusively to the webapp project so that the
Telegram bot can continue working with the existing cloud database.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func


Base = declarative_base()
metadata = Base.metadata


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    description = Column(Text)

    quizzes = relationship("Quiz", back_populates="category")


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    is_active = Column(Boolean, server_default=text("true"))
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"))
    description = Column(Text)

    category = relationship("Category", back_populates="quizzes")
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    results = relationship("Result", back_populates="quiz", cascade="all, delete-orphan")
    team_results = relationship("TeamResult", back_populates="quiz", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False)
    explanation = Column(Text)
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="CASCADE"))

    quiz = relationship("Quiz", back_populates="questions")
    options = relationship("Option", back_populates="question", cascade="all, delete-orphan")


class Option(Base):
    __tablename__ = "options"

    id = Column(Integer, primary_key=True)
    text = Column(Text, nullable=False)
    is_correct = Column(Boolean)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"))

    question = relationship("Question", back_populates="options")


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="SET NULL"))
    score = Column(Integer)
    time_taken = Column(Float)
    date_taken = Column(DateTime(timezone=False), server_default=func.now())

    user = relationship("User", back_populates="results")
    quiz = relationship("Quiz", back_populates="results")


class Team(Base):
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    code = Column(Text, nullable=False)
    captain_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    start_time = Column(DateTime(timezone=True))
    match_id = Column(Text)
    ready = Column(Boolean, server_default=text("false"))
    quiz_id = Column(Text)

    captain = relationship("User", back_populates="captain_of_teams", foreign_keys=[captain_id])
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    results = relationship("TeamResult", back_populates="team", cascade="all, delete-orphan")


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    is_captain = Column(Boolean, server_default=text("false"))
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="team_memberships", foreign_keys=[user_id])


class TeamResult(Base):
    __tablename__ = "team_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"))
    quiz_id = Column(Integer, ForeignKey("quizzes.id", ondelete="SET NULL"))
    score = Column(Integer, nullable=False)
    time_taken = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="results")
    quiz = relationship("Quiz", back_populates="team_results")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False, unique=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)

    results = relationship("Result", back_populates="user", cascade="all, delete-orphan")
    team_memberships = relationship("TeamMember", back_populates="user", cascade="all, delete-orphan")
    captain_of_teams = relationship("Team", back_populates="captain", cascade="all, delete-orphan")


__all__ = (
    "Base",
    "metadata",
    "Category",
    "Quiz",
    "Question",
    "Option",
    "Result",
    "Team",
    "TeamMember",
    "TeamResult",
    "User",
)