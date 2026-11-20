import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration

_HEADERS = {"X-Admin-Key": "integration-admin-key"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    url = os.getenv("DATABASE_TEST_URL", "").strip()
    if not url:
        pytest.skip("DATABASE_TEST_URL is not set")
    return TestClient(
        create_app(
            Settings(DATABASE_URL=url, IPO_STOCK_API_KEY="integration-admin-key")
        )
    )


def test_readiness_reaches_database(client: TestClient) -> None:
    assert client.get("/health/ready").status_code == 200


def test_list_and_detail_read_v_offerings(client: TestClient) -> None:
    listed = client.get("/api/v1/ipo-stocks?limit=5", headers=_HEADERS)

    assert listed.status_code == 200
    body = listed.json()
    assert body["summary"]["total"] >= body["count"] >= len(body["items"])
    for item in body["items"]:
        detail = client.get(f"/api/v1/ipo-stocks/{item['id']}", headers=_HEADERS)
        assert detail.status_code == 200
        assert detail.json()["id"] == item["id"]


@pytest.mark.parametrize(
    ("ipo_stock_id", "status_code"), [("-1", 404), ("not-a-number", 422)]
)
def test_detail_errors(client: TestClient, ipo_stock_id: str, status_code: int) -> None:
    response = client.get(f"/api/v1/ipo-stocks/{ipo_stock_id}", headers=_HEADERS)

    assert response.status_code == status_code
