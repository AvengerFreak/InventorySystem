import os
import sys
import time

# Ensure project root is on sys.path so this script can be run from the `tests/`
# directory and still import the `api` package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from api.main import app

# Ensure we use workspace credentials
os.environ.setdefault('USE_GOOGLE_DRIVE', '1')
os.environ.setdefault('GDRIVE_CREDENTIALS_PATH', os.path.join('environment', 'credentials.json'))
os.environ.setdefault('GDRIVE_FOLDER_ID')

with TestClient(app) as client:
    # Create a category
    resp = client.post('/categories/', json={'name': 'IntegrationCat', 'description': 'for integration test'}, headers={'X-User-Id': 'tester'})
    print('Create category:', resp.status_code, resp.text)
    cat = resp.json()
    cat_id = cat['id']

    # Create an item
    resp = client.post('/items/', json={'name': 'IntegrationItem', 'category_id': cat_id, 'description': 'test'}, headers={'X-User-Id': 'tester'})
    print('Create item:', resp.status_code, resp.text)
    item = resp.json()
    item_id = item['id']

    # Upload a small file
    files = {'file': ('test.png', b'PNGDATA', 'image/png')}
    resp = client.post(f'/items/{item_id}/image', files=files, headers={'X-User-Id': 'tester'})
    print('Upload response:', resp.status_code, resp.text)

    # Poll the item until image_file changes to what looks like a Drive id or timeout
    deadline = time.time() + 30
    while time.time() < deadline:
        resp = client.get(f'/items/{item_id}')
        if resp.status_code != 200:
            print('Failed to fetch item:', resp.status_code, resp.text)
            break
        data = resp.json()
        image_file = data.get('image_file')
        print('Current image_file:', image_file)
        # heuristics: Drive file ids are long and not equal to the original filename
        if image_file and not image_file.endswith('.png') and 'upload-test' not in image_file:
            print('Looks like Drive id:', image_file)
            break
        time.sleep(1)

    print('Integration test finished.')
