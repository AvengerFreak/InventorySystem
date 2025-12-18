"""Database helpers for the Inventory API.

Utilities provided:
- initialize the SQLite engine
- create sessions
- log history entries

The default local SQLite file is `database/database.db` (configurable via
the `SQLITE_FILE` environment variable). The module ensures the parent
directory exists before creating the SQLAlchemy engine so the database can
be created on first use.

Copyright (c) Bryn Gwalad 2025
"""

import os
from pathlib import Path
from typing import Optional
from datetime import datetime

from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine

# Load environment variables from .env if present
load_dotenv()

# Import History model (absolute import so this works when scripts run from
# different CWDs).
from api.models import History

# Default SQLite file location. Honor the SQLITE_FILE env var when set.
sqlite_file_name = os.getenv("SQLITE_FILE", "database/database.db")
sqlite_url = f"sqlite:///{sqlite_file_name}"

# Ensure parent directory exists before creating the engine
db_path = Path(sqlite_file_name)
try:
    db_path.parent.mkdir(parents=True, exist_ok=True)
except Exception:
    # If directory creation fails, let create_engine raise a clearer error
    # later rather than crashing during import.
    pass

# Create the engine (no echo by default)
engine = create_engine(sqlite_url, echo=False)

# Ensure tables exist on import. This is defensive: startup handlers also call
# `init_db()`, but tests (or scripts) that import the package and run
# endpoints directly may expect the tables to already exist.
try:
    SQLModel.metadata.create_all(engine)
except Exception:
    # If creation fails here, allow the runtime startup to attempt creation
    # again (avoids raising at import time in limited environments).
    pass


def init_db() -> None:
    """Create database tables from SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def log_history(table_operation: str, table_modified: str, user_id: str, modified_id: Optional[int] = None, session: Optional[Session] = None) -> None:
    """Create a History entry. If a Session is provided it will be used,
    otherwise a short-lived one will be created.

    The `id` is composed as: <table_modified>:<table_operation>:<user_id>:<YYYYmmddTHHMMSSffffff>
    """
    ts = datetime.utcnow()
    key = f"{table_modified}:{table_operation}:{user_id}:{ts.strftime('%Y%m%dT%H%M%S%f')}"
    entry = History(id=key, table_operation=table_operation, table_modified=table_modified, timestamp=ts, user_id=user_id, modified_id=modified_id)
    own_session = False
    if session is None:
        session = get_session()
        own_session = True
    try:
        session.add(entry)
        session.commit()
    finally:
        if own_session:
            session.close()
