import os
from logging.config import fileConfig
from pathlib import Path
from dotenv import load_dotenv  # ⬅️ добавь

# --- загружаем .env из корня проекта ---
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from alembic import context
from sqlalchemy import engine_from_config, pool
from core.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- теперь DATABASE_URL точно подхватится ---
database_url = os.getenv("SYNC_DATABASE_URL")
if not database_url:
    try:
        from core.database import DATABASE_URL as app_database_url
    except Exception:
        app_database_url = None
    database_url = app_database_url

if not database_url:
    raise RuntimeError("SYNC_DATABASE_URL environment variable must be set for Alembic migrations.")

config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()