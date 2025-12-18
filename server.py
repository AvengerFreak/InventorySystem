"""Server launcher for the Inventory API.

This module provides a small entrypoint to initialize the database and run
the FastAPI app via uvicorn.

Copyright (c) Bryn Gwalad 2025
"""

import os

from dotenv import load_dotenv

# Load .env from repo root so init_db picks up config
load_dotenv()

from utils.database import init_db

try:
    from api.main import app
except Exception as exc:
    raise RuntimeError(
        "Failed to import the FastAPI app. Ensure project root is on PYTHONPATH"
    ) from exc


def main() -> None:
    """Initialize DB and run uvicorn.

    Environment variables:
    - HOST: listen address (default 127.0.0.1)
    - PORT: listen port (default 8000)
    - RELOAD: set to '1' to enable uvicorn reload
    """

    # Initialize DB (creates tables if needed)
    init_db()

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "0") in ("1", "true", "True")

    # Start uvicorn programmatically
    import uvicorn

    uvicorn.run(app, host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
