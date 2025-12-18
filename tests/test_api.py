"""Tests for the Inventory API.

These tests exercise basic CRUD, image upload and history endpoints. Some
integration tests that touch Google Drive are optional and will skip if the
environment is not configured.

Copyright (c) Bryn Gwalad 2025
"""

# Ensure the project root is on sys.path so tests can be executed directly from
# the `tests/` directory (e.g. `python test_api.py`) and still import the
# `api` package.
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from datetime import datetime
import unittest

from fastapi.testclient import TestClient

from api.main import app


class InventoryAPITest(unittest.TestCase):
    """Unittests for the Inventory API. Using unittest lets you run all
    tests together (python -m unittest) or still run them via pytest.
    """

    @classmethod
    def setUpClass(cls):
        # TestClient is created once for the test class
        cls.client = TestClient(app)

    def test_basic_crud_and_inventory(self):
        # create category
        resp = self.client.post(
            "/categories/", json={"name": "Tools", "description": "Hand tools"}
        )
        self.assertEqual(resp.status_code, 200)
        cat = resp.json()
        self.assertIn("id", cat)
        cat_id = cat["id"]

        # create item
        resp = self.client.post(
            "/items/",
            json={"name": "Hammer", "category_id": cat_id, "description": "Heavy hammer"},
        )
        self.assertEqual(resp.status_code, 200)
        item = resp.json()
        self.assertEqual(item.get("name"), "Hammer")

        # inventory summary should include the category with at least 1 item
        resp = self.client.get("/inventory/")
        self.assertEqual(resp.status_code, 200)
        inventory = resp.json()
        self.assertTrue(any(entry.get("category_id") == cat_id for entry in inventory))

        # history should contain entries for the add operations (admin only)
        resp = self.client.get("/history/", headers={"X-User-Id": "admin"})
        self.assertEqual(resp.status_code, 200)
        history = resp.json()
        # we should have at least two history entries (one for category add, one for item add)
        self.assertGreaterEqual(len(history), 2)

    def test_upload_image_and_history(self):
        # create category
        resp = self.client.post(
            "/categories/", json={"name": "Gadgets", "description": "Electronics"}
        )
        self.assertEqual(resp.status_code, 200)
        cat = resp.json()
        cat_id = cat["id"]

        # create item
        resp = self.client.post(
            "/items/",
            json={"name": "Widget", "category_id": cat_id, "description": "Small widget"},
        )
        self.assertEqual(resp.status_code, 200)
        item = resp.json()
        item_id = item["id"]

        # upload image file
        files = {"file": ("pic.png", b"PNGDATA", "image/png")}
        resp = self.client.post(
            f"/items/{item_id}/image", files=files, headers={"X-User-Id": "tester"}
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("filename", body)
        self.assertIn("url", body)

        # ensure the Item row got the filename saved
        resp = self.client.get(f"/items/{item_id}")
        self.assertEqual(resp.status_code, 200)
        updated = resp.json()
        self.assertEqual(updated.get("image_file"), body["filename"])

        # history should include the update (admin only)
        resp = self.client.get("/history/?user_id=tester", headers={"X-User-Id": "admin"})
        self.assertEqual(resp.status_code, 200)
        hist = resp.json()
        self.assertTrue(any(h.get("table_modified") == "Item" and h.get("user_id") == "tester" for h in hist))

    def test_history_access_control_and_date_filter(self):
        # Without admin role, access is forbidden
        resp = self.client.get("/history/")
        self.assertEqual(resp.status_code, 403)

        resp = self.client.get("/history/", headers={"X-User-Id": "user"})
        self.assertEqual(resp.status_code, 403)

        # Admin can access; create an operation to ensure there is at least one entry today
        resp = self.client.post(
            "/categories/", json={"name": "TmpCat", "description": "tmp"}, headers={"X-User-Id": "admin"}
        )
        self.assertEqual(resp.status_code, 200)

        # date filter should accept YYYY-MM-DD
        today = datetime.utcnow().strftime("%Y-%m-%d")
        resp = self.client.get(
            f"/history/?date_from={today}&date_to={today}", headers={"X-User-Id": "admin"}
        )
        self.assertEqual(resp.status_code, 200)
        hist = resp.json()
        self.assertIsInstance(hist, list)


if __name__ == "__main__":
    # Allow running this test file directly
    unittest.main()
