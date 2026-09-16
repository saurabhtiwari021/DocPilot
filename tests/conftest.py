"""
Shared test fixtures.

Environment variables are set BEFORE anything under app/ is imported,
since app.config.settings.get_settings() is @lru_cache'd - once any
module reads settings, later os.environ changes are ignored for the
rest of the process. Using a fresh temp directory + temp sqlite file per
test session keeps tests isolated from any real data/ directory and from
each other.
"""

import os
import tempfile

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="docpilot-tests-")

os.environ["ENVIRONMENT"] = "development"
os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-not-for-prod"
os.environ["APP_DB_URL"] = f"sqlite:///{_TMP_DIR}/test.db"
os.environ["DOCUMENTS_BASE_DIR"] = f"{_TMP_DIR}/documents"
os.environ["LOCAL_CACHE_DIR"] = f"{_TMP_DIR}/cache"
os.environ["FAISS_INDEX_BASE_DIR"] = f"{_TMP_DIR}/vectorstore"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["VECTOR_STORE_BACKEND"] = "faiss"
os.environ["MAX_UPLOAD_SIZE_MB"] = "1"
os.environ["FRONTEND_URL"] = "https://example.com"
# Fast rate limits would make multi-request tests flaky against the real
# limiter, so keep them generous here - rate limiting itself isn't what
# these tests are checking.
os.environ["RATE_LIMIT_AUTH"] = "1000/minute"
os.environ["RATE_LIMIT_UPLOAD"] = "1000/minute"
os.environ["RATE_LIMIT_CHAT"] = "1000/minute"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _register_and_login(client: TestClient, username: str, password: str = "password123") -> str:
    client.post("/auth/register", json={"username": username, "password": password})
    resp = client.post("/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers_factory(client):
    """Returns a function that registers+logs in a fresh user and gives back auth headers."""

    def _make(username: str) -> dict:
        token = _register_and_login(client, username)
        return {"Authorization": f"Bearer {token}"}

    return _make
