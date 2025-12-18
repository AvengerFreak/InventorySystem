"""Database initialization helper.

Creates the configured SQLite database (when not using DATABASE_URL) and
emits SQL DDL into ``database/schema.sql``.

Copyright (c) Bryn Gwalad 2025
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `from api import models` works when
# running this script directly (python database/init_db.py).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlmodel import SQLModel, create_engine
from sqlalchemy.schema import CreateTable
from dotenv import load_dotenv

# Load environment variables from .env (so this script honors .env settings)
load_dotenv()

# Import application models after adjusting sys.path and loading env
from api import models  # noqa: F401 - models are registered via SQLModel metadata


def main() -> None:
    """Create the database and emit SQL DDL.

    The function reads ``DATABASE_URL`` or falls back to ``SQLITE_FILE``.
    """

    # determine database url (fall back to a local sqlite file)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        db_dir = Path("database")
        db_dir.mkdir(parents=True, exist_ok=True)
        sqlite_file = os.getenv("SQLITE_FILE", str(db_dir / "database.db"))
        database_url = f"sqlite:///{sqlite_file}"

    print(f"Using database URL: {database_url}")

    engine = create_engine(database_url, echo=True)

    # create all tables
    print("Creating tables...")
    SQLModel.metadata.create_all(engine)
    print("Tables created.")

    # emit SQL DDL to file
    schema_path = Path("database") / "schema.sql"
    print(f"Writing SQL DDL to {schema_path}")
    with open(schema_path, "w", encoding="utf-8") as f:
        for table in SQLModel.metadata.sorted_tables:
            ddl = str(CreateTable(table).compile(engine))
            f.write(ddl)
            f.write(";\n\n")

    print("Done.\n")


if __name__ == "__main__":
    main()
