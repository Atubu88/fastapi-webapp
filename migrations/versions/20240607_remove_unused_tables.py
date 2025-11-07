"""Drop unused tables to align with the simplified ORM models."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20240607_remove_unused_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("matching_quiz_results")
    op.drop_table("matching_quizzes")
    op.drop_table("poll_quiz_results")
    op.drop_table("poll_quiz_questions")
    op.drop_table("quiz_results")
    op.drop_table("quizzes_new")
    op.drop_table("self_report_tests")
    op.drop_table("settings")
    op.drop_table("survival_results")
    op.drop_table("user_attempts")


def downgrade() -> None:
    op.create_table(
        "user_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("quiz_id", sa.Integer(), nullable=True),
        sa.Column("selected_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
    )
    op.create_table(
        "survival_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("time_spent", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
    )
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("is_timer_enabled", sa.Boolean()),
    )
    op.create_table(
        "self_report_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("results", postgresql.JSONB()),
    )
    op.create_table(
        "quizzes_new",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("correct_order", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("difficulty", sa.Text(), server_default=sa.text("'не указана'")),
        sa.Column("extra_link", sa.Text()),
    )
    op.create_table(
        "quiz_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("quiz_id", sa.Integer(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("time_taken", sa.Float()),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
    )
    op.create_table(
        "poll_quiz_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("options", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("correct_answer", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text()),
        sa.Column("theme", sa.Text()),
    )
    op.create_table(
        "poll_quiz_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.Text()),
        sa.Column("score", sa.Integer(), server_default=sa.text("0")),
        sa.Column("time_spent", sa.Integer(), server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
    )
    op.create_table(
        "matching_quizzes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.Text()),
        sa.Column("pairs", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("telegraph_url", sa.Text()),
    )
    op.create_table(
        "matching_quiz_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quiz_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("error_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("time_taken", sa.Float()),
        sa.ForeignKeyConstraint(["quiz_id"], ["matching_quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
    )
