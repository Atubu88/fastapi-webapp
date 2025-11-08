"""CLI helper to initialize the local PostgreSQL database."""
from __future__ import annotations

import asyncio

from webapp.db.session import init_db


def main() -> None:
    asyncio.run(init_db())
    print("Database tables created successfully.")


if __name__ == "__main__":
    main()
