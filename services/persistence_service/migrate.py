import os

from .repository import SQLiteCXRepository


def main() -> None:
    path = os.getenv("DATABASE_PATH", "data/cx_phase1.db")
    SQLiteCXRepository(path).migrate()
    print(f"Applied Phase 1 migrations to {path}")


if __name__ == "__main__":
    main()
