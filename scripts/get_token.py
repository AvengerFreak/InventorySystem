"""Helper script to perform the OAuth InstalledAppFlow and write a token file.

Usage (PowerShell):
  python .\scripts\get_token.py --client secrets_oauth.json --output environment/token.json

The script requires `google-auth-oauthlib` to be installed in your environment.
It will open a browser for interactive consent and write the resulting token JSON.
"""
import argparse
import os

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except Exception:
    raise SystemExit("google-auth-oauthlib is required. Install with: pip install google-auth-oauthlib")

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--client", default="environment/credentials_oauth.json", help="OAuth client JSON file (from Google Cloud Console)")
    p.add_argument("--output", default="environment/token.json", help="Where to write the user token JSON")
    args = p.parse_args()

    if not os.path.exists(args.client):
        raise SystemExit(f"Client JSON not found at {args.client}")

    flow = InstalledAppFlow.from_client_secrets_file(args.client, SCOPES)
    creds = flow.run_local_server(port=0)

    # ensure output dir exists
    outdir = os.path.dirname(args.output)
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        import json

        json.dump(
            {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes,
            },
            f,
        )
    print(f"Wrote user token to {args.output}")


if __name__ == "__main__":
    main()
