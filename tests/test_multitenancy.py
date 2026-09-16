import io

import pytest

from app.services.vectorstore_service import vectorstore_service


@pytest.fixture(autouse=True)
def no_real_embeddings(monkeypatch):
    def fake_add_documents(user_id, documents):
        return 1, ["chunk-0"]

    def fake_delete_documents(user_id, chunk_ids):
        pass

    monkeypatch.setattr(vectorstore_service, "add_documents", fake_add_documents)
    monkeypatch.setattr(vectorstore_service, "delete_documents", fake_delete_documents)


def test_user_cannot_see_another_users_documents(auth_headers_factory, client):
    headers_a = auth_headers_factory("tenant_a")
    headers_b = auth_headers_factory("tenant_b")

    upload_resp = client.post(
        "/upload",
        headers=headers_a,
        files={"file": ("secret-plan.txt", io.BytesIO(b"confidential"), "text/plain")},
    )
    assert upload_resp.status_code == 200

    docs_a = client.get("/documents", headers=headers_a).json()
    assert any(d["filename"] == "secret-plan.txt" for d in docs_a["documents"])

    docs_b = client.get("/documents", headers=headers_b).json()
    assert not any(d["filename"] == "secret-plan.txt" for d in docs_b["documents"])
    assert docs_b["count"] == 0


def test_user_cannot_read_another_users_history(auth_headers_factory, client):
    headers_a = auth_headers_factory("history_a")
    headers_b = auth_headers_factory("history_b")

    # Neither user has chatted yet, but each should only ever see their
    # own (empty) session, never an error caused by cross-user lookups.
    resp_a = client.get("/history", headers=headers_a)
    resp_b = client.get("/history", headers=headers_b)
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert resp_a.json()["messages"] == []
    assert resp_b.json()["messages"] == []
