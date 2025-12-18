import os
import sys
import tempfile

# Ensure project root is on sys.path so scripts run from `tests/` can import package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Use credentials and folder id from environment variables or fall back to environment/ paths
creds_path = os.getenv('GDRIVE_CREDENTIALS_PATH', os.path.join('environment', 'credentials.json'))
folder_id = os.getenv('GDRIVE_FOLDER_ID')

print('Using credentials:', creds_path)
print('Using folder id:', folder_id)

if not os.path.exists(creds_path):
    raise SystemExit(f"Credentials file not found: {creds_path}")

creds = Credentials.from_service_account_file(creds_path, scopes=['https://www.googleapis.com/auth/drive'])
service = build('drive', 'v3', credentials=creds)

# upload a tiny file
with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as tf:
    tf.write(b'test-drive-upload')
    tf.flush()
    tmpname = tf.name

media = MediaFileUpload(tmpname, mimetype='text/plain')
file_metadata = {'name': 'upload-test-from-script.txt', 'parents': [folder_id]}
print('Uploading test file...')
f = service.files().create(body=file_metadata, media_body=media, fields='id, name', supportsAllDrives=True).execute()
print('Uploaded:', f)

# list files in folder (first 20)
res = service.files().list(q=f"'{folder_id}' in parents", pageSize=20, fields='files(id, name)', supportsAllDrives=True).execute()
print('Files in folder:')
for fi in res.get('files', []):
    print('-', fi)

print('Done.')
