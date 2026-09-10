"""Opt-in integration test against a disposable, running Compose stack.

PRISLAPP_TEST_URL=http://localhost:18000 pytest tests/test_live_pipeline.py -v
"""
import os
import time
import uuid
from pathlib import Path

import httpx
import pytest


@pytest.mark.skipif(not os.getenv("PRISLAPP_TEST_URL"), reason="Requires disposable Compose stack")
def test_live_ocr_confirmation_prices_and_delete():
    with httpx.Client(base_url=os.environ["PRISLAPP_TEST_URL"], timeout=60) as client:
        response = client.post("/auth/register", json={
            "email": f"pipeline-{uuid.uuid4().hex}@example.com", "password": "PipelineTest123!",
        })
        assert response.status_code == 201
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        image = Path(__file__).parents[2] / "testdata/receipts/rema1000-metro-senter.png"
        captures = []
        try:
            for _ in range(3):
                key = str(uuid.uuid4())
                for _ in range(2):
                    upload = client.post("/receipts", headers={**headers, "Idempotency-Key": key},
                                         files={"file": (image.name, image.read_bytes(), "image/png")})
                    assert upload.status_code == 201, upload.text
                    assert upload.json()["id"] == key
                captures.append(key)
            for receipt_id in captures:
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    detail = client.get(f"/receipts/{receipt_id}", headers=headers).json()
                    if detail["status"] in {"READY_FOR_REVIEW", "FAILED"}:
                        break
                    time.sleep(2)
                assert detail["status"] == "READY_FOR_REVIEW", detail
                assert len(detail["items"]) == 7
                confirm = client.put(f"/receipts/{receipt_id}/confirm", headers=headers, json={
                    "store_name": "Integration test store", "purchase_date": "2026-08-04T18:41:00Z",
                    "total": detail["total"], "items": detail["items"],
                })
                assert confirm.status_code == 200, confirm.text
                assert confirm.json()["store"]["name"] == "Integration test store"
            products = client.get("/products/search?q=lettmelk", headers=headers).json()["items"]
            prices = client.get(f"/products/{products[0]['id']}/my-prices", headers=headers).json()
            assert len(prices["observations"]) == 3
            assert prices["cheapest"]["price"] == "31.40"
        finally:
            for receipt_id in captures:
                assert client.delete(f"/receipts/{receipt_id}", headers=headers).status_code == 204
