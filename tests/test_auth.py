from fastapi.testclient import TestClient

from app.main import create_app


def test_me_requires_bearer_token() -> None:
    response = TestClient(create_app()).get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_me_reports_authentication_service_unavailable() -> None:
    response = TestClient(create_app()).get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer token-123"}
    )

    assert response.status_code == 503
    assert response.json()["code"] == "authentication_service_unavailable"
    assert "token-123" not in response.text
