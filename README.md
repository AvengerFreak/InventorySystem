# Inventory FastAPI

Simple inventory API with Category and Item models using FastAPI and SQLModel (SQLite).

Run locally:

1. Create a virtual environment and activate it (optional but recommended).
2. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

3. Run the app:

You can start the app with the provided `server.py` helper or run uvicorn directly.

```powershell
# using the helper (initializes DB then starts the server)
python server.py

# or run uvicorn directly
python -m uvicorn api.main:app --reload
```

Environment variables
- `SQLITE_FILE` (optional): when `DATABASE_URL` is not set, use this filename for a local SQLite DB (default `database/database.db`).
- `ADMIN_USERS` (optional): comma-separated list of admin user ids (default: `admin`). The `/history/` endpoint checks the `X-User-Id` header is in this list.
- `IMAGE_BASE_URL` (optional): base URL used to construct image URLs. Default is Google Drive view pattern `https://drive.google.com/uc?export=view&id=`.
- `GDRIVE_CREDENTIALS_PATH` / `GDRIVE_FOLDER_ID`: the service-account JSON path and target folder id. The app will always attempt to upload files to Google Drive (see notes below).

Example (PowerShell):

```powershell
$env:ADMIN_USERS = 'webminister,deputy_webminister'
$env:IMAGE_BASE_URL = 'https://drive.google.com/uc?export=view&id='
python -m uvicorn api.main:app --reload
```

.env support
- You can put environment variables in a `.env` file at the project root. The app and helper scripts will automatically load variables from `.env` (via python-dotenv).
- Example `.env`:

```text
ADMIN_USERS=admin,alice
USE_GOOGLE_DRIVE=0
IMAGE_BASE_URL=https://drive.google.com/uc?export=view&id=
SQLITE_FILE=database/database.db
# or DATABASE_URL=sqlite:///C:/path/to/database.db
```

If you create a `.env` file, you can start the app normally and it will pick up the variables.

Initialize database and write SQL scripts

The repository includes a helper script that creates the configured database file and writes SQL DDL for all tables into `database/schema.sql`.

Run it like this (uses the same env vars as the app):

```powershell
python database/init_db.py
```

API highlights:
- Category: id, name, description
- Item: id, name, category_id, description, image_file (stores filename or file id)
- Inventory summary endpoint at `/inventory/` (counts per category)

Images / Google Drive
- The API stores only the `image_file` value in the database. The full URL returned by the API is constructed as IMAGE_BASE_URL + image_file.
- By default the app uses a Google Drive friendly base URL: `https://drive.google.com/uc?export=view&id=`. This assumes `image_file` contains the Google Drive file id. If you plan to store plain filenames in a public folder, set IMAGE_BASE_URL to your public folder base URL.
- To configure the base URL, set the `IMAGE_BASE_URL` environment variable before starting the app.

Automatic Google Drive uploads

The app always attempts to upload uploaded images to Google Drive and will update the `image_file` column with the resulting Drive file id when successful. If the credentials are missing or the upload fails the API will keep the local filename in the DB so the endpoint still returns a usable URL.

Recommended production approach: use a Google service account. Create a service account in Google Cloud Console, grant it access to the target Drive (or a shared folder), and download the service account JSON key file. Place the key file somewhere secure and set `GDRIVE_CREDENTIALS_PATH` to that path.

Quick setup (service account):

1) Ensure Drive libraries are installed (they're included in `requirements.txt`):

```powershell
python -m pip install -r requirements.txt
```

2) Create a Google Cloud service account and download the JSON key. Save it as `service-account.json` (or choose another path).

3) Configure environment variables before starting the API (replace paths/ids as needed):

```powershell
$env:GDRIVE_CREDENTIALS_PATH = 'service-account.json'
$env:GDRIVE_FOLDER_ID = '<folder id to upload into>'
$env:IMAGE_BASE_URL = 'https://drive.google.com/uc?export=view&id='
python server.py
```

Notes:
- The background uploader uses the service account JSON specified by `GDRIVE_CREDENTIALS_PATH` to authenticate.
- The service account must have access to the target Drive or shared folder. For public access to uploaded files the service account or destination folder must allow creating files with reader=anyone permissions.
 -Notes:
 - The background uploader uses the service account JSON specified by `GDRIVE_CREDENTIALS_PATH` to authenticate.
 - Important: when using a Google service account you cannot reliably upload into a personal "My Drive" folder because service accounts do not have personal storage quota. If your target folder is inside a personal My Drive you will likely see a 403 with a message about storage quota.

 Recommended approaches:
 - Use a Shared Drive (Team Drive) and add the service account email as a member with Content Manager access. Files uploaded to a Shared Drive do not consume a service account's personal storage quota and are the recommended approach for automated service-account uploads.
 - Alternatively, use OAuth user credentials or domain-wide delegation to impersonate a real user in your Google Workspace domain (requires admin setup).

 How to use a Shared Drive (UI):
 1. In Google Drive, create a Shared Drive (left sidebar > Shared drives > New).
 2. Open the target folder in the Shared Drive and copy its folder id from the URL (the part after `/folders/`).
 3. Share the folder or Shared Drive with the service-account email (found in your service-account JSON under `client_email`) and grant Editor/Content manager permissions.
 4. Set `GDRIVE_FOLDER_ID` to the folder id you copied and restart the server.

 After switching to a Shared Drive, uploads from the service account should succeed. If you continue to see 403 errors, check the server logs for the Drive API error details which will include the reason and suggested remediation.
Background uploader
- The app contains a background uploader that processes uploaded files and (when enabled) sends them to Google Drive asynchronously. The upload task runs in the background and updates the `image_file` DB value with the Drive file id when completed.
- The background uploader is started automatically when the FastAPI app starts. If you prefer synchronous uploads, set `USE_GOOGLE_DRIVE` to `0`.

Troubleshooting notes
- If you see Drive upload failures in logs, check that `GDRIVE_CREDENTIALS_PATH` points to a valid service account JSON and that the service account has permission to create files in the target folder.
- For production automation, prefer a service account or a secure secret store for service-account keys. Do not commit credentials to source control.

Notes:
- The app attempts to set sharing permissions so the uploaded file is viewable by anyone with the link; this may require the target folder to allow public sharing.
- If Drive upload fails for any reason the API falls back to storing the local filename; this ensures the endpoint remains usable in environments without Drive configured.

Tests:

```powershell
python -m pytest -q
```

Database: a local SQLite file `database/database.db` is created in the `database/` directory on first run (unless `SQLITE_FILE` or `DATABASE_URL` are set).

Postman collection
------------------

A Postman collection for this API is included under `postman/InventoryAPI.postman_collection.json`.

How to use:

1. Import the collection file into Postman (File -> Import -> choose `postman/InventoryAPI.postman_collection.json`).
2. Create or select an environment and set the `base_url` variable if your server runs on a different host/port (default is `http://localhost:8000`).
3. Set `user_id` to a test user (use `admin` for history endpoints).
4. For file uploads, set `file_path` in the environment (or attach a file in Postman's form-data body when executing the request).

Mock server
-----------

The collection includes example responses for each request which you can use to create a mock server in Postman. After importing the collection, create a mock from the collection and Postman will expose a `mock_server` URL [mock-server](https://e6f06fd3-b15c-42ee-9c80-d5c87e6dc0a7.mock.pstmn.io); you can set the environment `base_url` to the mock server URL to exercise example responses without running the API locally.
