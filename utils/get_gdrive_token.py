"""Interactive helper to create an OAuth token.json for Google Drive access.

This utility uses the Installed App flow and is suitable when you need to
obtain a user token for a personal Google account. For automated server-side
usage prefer a service account and set ``GDRIVE_CREDENTIALS_PATH`` accordingly.

Copyright (c) Bryn Gwalad 2025
"""

from __future__ import print_function
import os
from typing import Optional

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except Exception:  # pragma: no cover - optional helper
    InstalledAppFlow = None

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> None:
    """Run the installed-app OAuth flow and write the token to disk.

    Environment variables:
        GDRIVE_CREDENTIALS_PATH: path to OAuth client secrets JSON
        GDRIVE_TOKEN_PATH: path where the token JSON will be written
    """
    if InstalledAppFlow is None:
        print("google-auth-oauthlib is not installed; cannot run interactive flow.")
        return

    creds_path = os.getenv("GDRIVE_CREDENTIALS_PATH", "credentials.json")
    token_path = os.getenv("GDRIVE_TOKEN_PATH", "token.json")

    if not os.path.exists(creds_path):
        print(f"Missing credentials file: {creds_path}")
        print(
            "Create OAuth client credentials in Google Cloud Console (Desktop app)"
        )
        return

    flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, "w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())

    print(f"Saved token to {token_path}")


if __name__ == "__main__":
    main()
