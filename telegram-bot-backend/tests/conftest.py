from __future__ import annotations

import hashlib
import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256(ADMIN_PASSWORD.encode("utf-8")).hexdigest()

os.environ.setdefault("POSTGRES_DSN", "postgresql+asyncpg://bot_user:bot_pass@localhost:5432/bot_db")
os.environ.setdefault("REDIS_DSN", "redis://localhost:6379/0")
os.environ.setdefault("SALES_BOT_TOKEN", "test-token")
os.environ["ADMIN_USERNAME"] = ADMIN_USERNAME
os.environ["ADMIN_PASSWORD_HASH"] = ADMIN_PASSWORD_HASH

from app.api.main import app


@pytest.fixture(scope="module")
def admin_client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        response = client.post(
            "/admin/login",
            data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200
        yield client