"""HTTP API for the Inventory service.

Provides endpoints for Category and Item CRUD, image uploads and history
queries. The module starts a background uploader to optionally push images to
Google Drive when configured.

Copyright (c) Bryn Gwalad 2025
"""

from typing import List, Optional
import os
import shutil
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException, Query, UploadFile, File
from fastapi.encoders import jsonable_encoder
from sqlmodel import select
from dotenv import load_dotenv
import logging

# Load environment variables from a .env file at project root if present.
load_dotenv()

from utils.database import engine, init_db, get_session, log_history
from .models import Category, Item, History

# Optional Google client libraries are imported at module import time and
# gracefully disabled if not present. This allows the module to be imported
# even when the google packages are not installed.
try:
    from google.oauth2.service_account import (
        Credentials as ServiceAccountCredentials,
    )
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except Exception:  # pragma: no cover - optional dependency
    ServiceAccountCredentials = None
    build = None
    MediaFileUpload = None


# Configuration: base URL for Google Drive where images are served.
# The API stores only filenames in the DB and constructs full URLs by joining
# this base and the stored filename. Make this configurable via the
# IMAGE_BASE_URL environment variable. NOTE: Google Drive typically serves
# files by file-id rather than filename; if you plan to upload files to
# Google Drive automatically, prefer returning the file's shareable URL or
# file id from the upload flow and store that value in `image_file`.
# Default below is a common Google Drive "view by id" pattern; it assumes
# the stored `image_file` is a file id. If your workflow stores plain
# filenames instead, set IMAGE_BASE_URL to your public folder's base URL.
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "https://drive.google.com/uc?export=view&id=")

# Local uploads folder used as a placeholder for file storage in this example.
# In production the API would upload to OneDrive and not necessarily keep local copies.
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Admin users configuration: comma-separated list in env ADMIN_USERS, fallback to ['admin']
ADMIN_USERS = [u.strip() for u in os.getenv("ADMIN_USERS", "admin").split(",") if u.strip()]

app = FastAPI(title="Inventory API")

# Module logger
logger = logging.getLogger("inventory_api")



def _serialize_category(cat: Category) -> dict:
    """Convert a Category ORM instance into a JSON-serializable dict.

    We avoid relying on Pydantic/SQLModel JSON encoding here because ORM
    instances may be detached when FastAPI attempts to validate/serialize
    them. Return a minimal, explicit representation.
    """
    # Keep this representation minimal and avoid touching related
    # relationship attributes (like `items`) which may be lazy-loaded and
    # cause DetachedInstanceError if the session is closed. If callers need
    # related data, provide a dedicated endpoint that queries it explicitly.
    return {
        "id": cat.id,
        "name": cat.name,
        "description": cat.description,
    }


def _serialize_item(item: Item) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "category_id": item.category_id,
        "description": item.description,
        "image_file": item.image_file,
    }


@app.on_event("startup")
async def on_startup():
    """Application startup handler.

    Initializes the database and starts the background uploader queue.
    """
    # initialize DB
    init_db()

    # Configure logger (do not override global config if already set by app)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)

    # Drive uploader configuration. The background uploader is always started
    # and will attempt to upload any enqueued jobs to Google Drive. If the
    # service account credentials are missing or invalid the uploader will
    # log errors and the local filename will remain in the DB.
    creds_path = os.getenv("GDRIVE_CREDENTIALS_PATH", "credentials.json")
    folder_id = os.getenv("GDRIVE_FOLDER_ID")
    logger.info("Google Drive uploader starting; credentials=%s folder=%s", creds_path, folder_id)

    # create an upload queue and start background uploader (always started,
    # it will only process jobs when USE_GOOGLE_DRIVE is enabled). This keeps
    # behavior consistent between dev and prod.
    app.state.upload_queue = asyncio.Queue()
    app.state.uploader_task = asyncio.create_task(_background_uploader(app.state.upload_queue))


@app.post("/categories/")
def create_category(category: Category, user_id: str = Header("system", alias="X-User-Id")):
    """Create a new Category.

    The request must include a JSON Category object. The `X-User-Id` header is
    used for audit logging.
    """
    with get_session() as session:
        session.add(category)
        session.commit()
        session.refresh(category)
        # log history
        log_history("add", "Category", user_id, modified_id=category.id, session=session)
        # serialize while session is still open to avoid lazy-loading after detach
        return _serialize_category(category)


@app.get("/categories/")
def list_categories():
    """Return a list of all categories."""
    with get_session() as session:
        cats = session.exec(select(Category)).all()
        return [_serialize_category(c) for c in cats]


@app.get("/categories/{category_id}")
def get_category(category_id: int):
    """Return a category by id or raise 404 if not found."""
    with get_session() as session:
        category = session.get(Category, category_id)
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        return _serialize_category(category)


@app.put("/categories/{category_id}")
def update_category(category_id: int, category: Category, user_id: str = Header("system", alias="X-User-Id")):
    """Update an existing category.

    The `X-User-Id` header is used for audit logging.
    """
    with get_session() as session:
        db = session.get(Category, category_id)
        if not db:
            raise HTTPException(status_code=404, detail="Category not found")
        db.name = category.name
        db.description = category.description
        session.add(db)
        session.commit()
        session.refresh(db)
        log_history("update", "Category", user_id, modified_id=db.id, session=session)
        return _serialize_category(db)


@app.delete("/categories/{category_id}")
def delete_category(category_id: int, user_id: str = Header("system", alias="X-User-Id")):
    """Delete a category by id. Records an audit entry using X-User-Id."""
    with get_session() as session:
        db = session.get(Category, category_id)
        if not db:
            raise HTTPException(status_code=404, detail="Category not found")
        session.delete(db)
        session.commit()
        log_history("delete", "Category", user_id, modified_id=category_id, session=session)
        return {"ok": True}


@app.post("/items/")
def create_item(item: Item, user_id: str = Header("system", alias="X-User-Id")):
    """Create a new Item. Validates category exists when provided.

    Uses `X-User-Id` for audit logging.
    """
    with get_session() as session:
        if item.category_id is not None and not session.get(Category, item.category_id):
            raise HTTPException(status_code=400, detail="Category does not exist")
        session.add(item)
        session.commit()
        session.refresh(item)
        log_history("add", "Item", user_id, modified_id=item.id, session=session)
        return _serialize_item(item)


@app.get("/items/")
def list_items(category_id: Optional[int] = Query(default=None)):
    """List items, optionally filtered by category_id."""
    with get_session() as session:
        q = select(Item)
        if category_id is not None:
            q = q.where(Item.category_id == category_id)
        items = session.exec(q).all()
        return [_serialize_item(i) for i in items]


@app.get("/items/{item_id}")
def get_item(item_id: int):
    """Return an item by id or raise 404 if not found."""
    with get_session() as session:
        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return _serialize_item(item)


@app.post("/items/{item_id}/image")
def upload_item_image(item_id: int, file: UploadFile = File(...), user_id: str = Header("system", alias="X-User-Id")):
    """Save upload locally, store filename immediately, and enqueue background upload job."""
    with get_session() as session:
        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # derive category id (use 0 if none)
        category_id = item.category_id if item.category_id is not None else 0

        # compute timestamp and extension
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        original = file.filename or "upload"
        ext = os.path.splitext(original)[1] or ""
        filename = f"{category_id}-{item_id}-{ts}{ext}"

        # write file to uploads dir
        dest_path = UPLOAD_DIR / filename
        try:
            with open(dest_path, "wb") as dest:
                shutil.copyfileobj(file.file, dest)
        finally:
            file.file.close()

        # store the filename locally immediately
        item.image_file = filename
        session.add(item)
        session.commit()
        session.refresh(item)

        # enqueue background upload job (uploader will attempt Drive upload)
        job = {
            "item_id": item.id,
            "path": str(dest_path),
            "filename": filename,
            "content_type": file.content_type,
            "user_id": user_id,
        }
        try:
            app.state.upload_queue.put_nowait(job)
            logger.info("Enqueued upload job for item=%s path=%s", item.id, job["path"])
        except Exception:
            # queue full or not available; leave file for manual processing
            logger.exception("Failed to enqueue upload job for item=%s", item.id)
            pass

        # initial update logged (local filename set)
        log_history("update", "Item", user_id, modified_id=item.id, session=session)

        return {"filename": item.image_file, "url": IMAGE_BASE_URL + item.image_file}


@app.get("/items/{item_id}/image")
def get_item_image_url(item_id: int):
    """Return the full image URL for an item (constructed from IMAGE_BASE_URL + filename).
    Returns 404 if item or filename not present.
    """
    with get_session() as session:
        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if not item.image_file:
            raise HTTPException(status_code=404, detail="No image for item")
        return {"filename": item.image_file, "url": IMAGE_BASE_URL + item.image_file}


@app.get("/history/", response_model=List[History])
def get_history(
    user_id: Optional[str] = None,
    table_modified: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    x_user_id: str = Header("system", alias="X-User-Id"),
):
    """Return history entries.

    Access control: only callers with X-User-Id present in ADMIN_USERS may read history.

    Filtering:
    - `user_id` exact match
    - `table_modified` exact match ("Category" or "Item")
    - `date_from` and `date_to` are ISO dates (YYYY-MM-DD) or datetimes and filter on the `timestamp` field inclusive.
    - `limit` and `offset` provide pagination.
    """
    # enforce admin-only access via configured ADMIN_USERS
    if x_user_id not in ADMIN_USERS:
        raise HTTPException(status_code=403, detail="admin user required to access history")

    # parse optional date filters
    dt_from = None
    dt_to = None
    try:
        if date_from:
            dt_from = datetime.fromisoformat(date_from)
        if date_to:
            dt_to = datetime.fromisoformat(date_to)
            # if date only (YYYY-MM-DD) was provided, include entire day
            if len(date_to) == 10:
                dt_to = dt_to + timedelta(days=1) - timedelta(microseconds=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from/date_to must be ISO format (YYYY-MM-DD or full ISO datetime)")

    # Build SQL query with filters
    q = select(History)
    if user_id is not None:
        q = q.where(History.user_id == user_id)
    if table_modified is not None:
        q = q.where(History.table_modified == table_modified)
    if dt_from is not None:
        q = q.where(History.timestamp >= dt_from)
    if dt_to is not None:
        q = q.where(History.timestamp <= dt_to)

    # order by timestamp desc (most recent first)
    q = q.order_by(History.timestamp.desc()).offset(offset).limit(limit)

    with get_session() as session:
        results = session.exec(q).all()
        return results


@app.get("/inventory/")
def inventory_summary():
    """Return count of items per category and unassigned items."""
    with get_session() as session:
        categories = session.exec(select(Category)).all()
        result = []
        for cat in categories:
            items = session.exec(select(Item).where(Item.category_id == cat.id)).all()
            result.append({"category_id": cat.id, "category_name": cat.name, "item_count": len(items)})
        # unassigned
        unassigned = session.exec(select(Item).where(Item.category_id == None)).all()
        if len(unassigned) > 0:
            result.append({"category_id": None, "category_name": "Unassigned", "item_count": len(unassigned)})
        return result


async def _background_uploader(queue: asyncio.Queue):
    """Background worker that processes upload jobs from the queue.

    Each job is a dict with keys: item_id, path, filename, content_type, user_id.
    The worker attempts to upload to Google Drive using credentials at GDRIVE_TOKEN_PATH
    and replaces the `image_file` value in the DB with the resulting Drive file id on success.
    """
    while True:
        job = await queue.get()
        try:
            # run the blocking upload+db update in a thread
            await asyncio.to_thread(_process_upload_job, job)
        except Exception:
            # log exception; job can be retried by external tooling if desired
            logger.exception("Background uploader failed processing job: %s", job)
        finally:
            try:
                queue.task_done()
            except Exception:
                pass


def _process_upload_job(job: dict):
    """Synchronous helper that uploads a file to Google Drive and updates the DB.

    Designed to be run inside a thread via asyncio.to_thread().
    """
    creds_path = os.getenv("GDRIVE_CREDENTIALS_PATH", "credentials.json")
    folder_id = os.getenv("GDRIVE_FOLDER_ID")
    logger.info("Processing upload job for item=%s path=%s -> folder=%s", job.get("item_id"), job.get("path"), folder_id)

    # import Google libs lazily
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except Exception:
        logger.exception("Google API client libraries are not installed; cannot upload to Drive")
        return

    # Prefer a user OAuth token if present (interactive flow produced token.json).
    # This supports uploading as a real user (including consumer Gmail accounts).
    token_path = os.getenv("GDRIVE_TOKEN_PATH", "environment/token.json")
    service = None
    if os.path.exists(token_path):
        try:
            from google.oauth2.credentials import Credentials as UserCredentials

            logger.info("Using OAuth token from %s to build Drive client", token_path)
            creds = UserCredentials.from_authorized_user_file(token_path, scopes=["https://www.googleapis.com/auth/drive"])  # type: ignore[arg-type]
            service = build("drive", "v3", credentials=creds)
        except Exception:
            logger.exception("Failed to load user OAuth token from %s; falling back to service account", token_path)

    # If no user token or loading failed, fall back to service account credentials
    if service is None:
        try:
            from google.oauth2.service_account import Credentials as ServiceAccountCredentials

            if not os.path.exists(creds_path):
                logger.error("GDrive credentials file not found at %s; skipping upload for job=%s", creds_path, job)
                return

            creds = ServiceAccountCredentials.from_service_account_file(creds_path, scopes=["https://www.googleapis.com/auth/drive"])
            # If domain-wide delegation/impersonation is configured, allow the
            # service account to act on behalf of a user by using the
            # GDRIVE_IMPERSONATE_USER env var. This requires domain-wide
            # delegation to be enabled for the service account in Google Workspace
            # admin console and the client_id granted the Drive scopes.
            subject = os.getenv("GDRIVE_IMPERSONATE_USER")
            if subject:
                try:
                    creds = creds.with_subject(subject)
                    logger.info("Impersonating user %s for Drive uploads", subject)
                except Exception:
                    logger.exception("Failed to apply subject impersonation for %s", subject)

            service = build("drive", "v3", credentials=creds)
        except Exception:
            logger.exception("Failed to load service account credentials from %s", creds_path)
            return
        media = MediaFileUpload(job.get("path"), mimetype=job.get("content_type") or "application/octet-stream")
        body = {"name": job.get("filename")}
        if folder_id:
            body["parents"] = [folder_id]
        # Perform upload and handle Drive-specific HTTP errors explicitly to
        # provide actionable diagnostics (e.g. service accounts and storage
        # quota restrictions).
        try:
            # If uploading into a Shared Drive (recommended for service accounts)
            # the API calls must set supportsAllDrives=True so the Drive API will
            # allow creating files inside that shared drive. This parameter is
            # harmless for My Drive uploads and is required for service account
            # workflows that target Shared Drives.
            created = service.files().create(
                body=body,
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            ).execute()
        except Exception as e:
            # Try to import HttpError for richer diagnostics, but don't fail if
            # the import isn't available.
            try:
                from googleapiclient.errors import HttpError
            except Exception:
                HttpError = None

            if HttpError is not None and isinstance(e, HttpError):
                # HttpError content is bytes/str with JSON details in many cases
                logger.error("Drive upload HttpError for job=%s: %s", job, e)
                # Specific common case: service accounts have no personal storage
                # quota for My Drive; suggest using a Shared Drive or OAuth.
                if hasattr(e, 'resp') and getattr(e.resp, 'status', None) == 403:
                    logger.error(
                        "Drive API returned 403. Common cause: service accounts do not have personal storage quota for My Drive.\n"
                        "Options: use a Shared Drive (Team Drive) and give the service account permission, or use OAuth user credentials/domain-wide delegation.\n"
                        "See README for more details: GDRIVE_FOLDER_ID should point to a Shared Drive folder when using a service account."
                    )
            else:
                logger.exception("Exception while creating Drive file for job=%s", job)
            return
        file_id = created.get("id")
        if not file_id:
            logger.error("Drive upload did not return file id for job=%s; response=%s", job, created)
            return

        # try set public reader permission; not critical so we log but continue on failure
        try:
            # When setting permissions on Shared Drive files specify
            # supportsAllDrives so the operation succeeds for Shared Drive files.
            service.permissions().create(
                fileId=file_id,
                body={"role": "reader", "type": "anyone"},
                supportsAllDrives=True,
            ).execute()
        except Exception:
            logger.warning("Could not set public permission for file %s (job=%s)", file_id, job)

        # update DB and log
        try:
            with get_session() as session:
                item = session.get(Item, job.get("item_id"))
                if item:
                    item.image_file = file_id
                    session.add(item)
                    session.commit()
                    session.refresh(item)
                    log_history("update", "Item", job.get("user_id", "system"), modified_id=item.id, session=session)
                    logger.info("Updated DB item=%s image_file=%s", item.id, file_id)
                else:
                    logger.error("Item not found in DB when updating after Drive upload: %s", job.get("item_id"))
        except Exception:
            logger.exception("Failed to update DB after Drive upload for job=%s", job)

        # remove local file
        try:
            os.remove(job.get("path"))
            logger.info("Removed local file %s after successful upload", job.get("path"))
        except Exception:
            logger.warning("Failed to remove local file %s after upload", job.get("path"))
    


@app.on_event("shutdown")
async def on_shutdown():
    # gracefully cancel uploader task
    task = getattr(app.state, "uploader_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
