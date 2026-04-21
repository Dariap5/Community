import os

os.environ.setdefault("POSTGRES_DSN", "postgresql+asyncpg://bot_user:bot_pass@localhost:5432/bot_db")
os.environ.setdefault("REDIS_DSN", "redis://localhost:6379/0")
os.environ.setdefault("SALES_BOT_TOKEN", "test-token")

from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_swagger_ui_is_served() -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()


def test_openapi_contains_key_routes() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    expected_paths = {
        "/health",
        "/api/funnels",
        "/api/funnels/{funnel_id}",
        "/api/funnels/{funnel_id}/duplicate",
        "/api/funnels/{funnel_id}/restore",
        "/api/funnels/{funnel_id}/steps",
        "/api/funnels/{funnel_id}/steps/{step_id}",
        "/api/funnels/{funnel_id}/steps/{step_id}/duplicate",
        "/api/funnels/{funnel_id}/steps/reorder",
        "/api/payments/webhook",
    }

    assert expected_paths.issubset(paths.keys())