"""CLI helper to initialize the local PostgreSQL database."""
from __future__ import annotations

from webapp.database import init_db


def main() -> None:
    init_db()
    print("Database tables created successfully.")


if __name__ == "__main__":
    main()
