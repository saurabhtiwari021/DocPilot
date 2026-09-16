import io

import pytest

from app.services.vectorstore_service import vectorstore_service


@pytest.fixture(autouse=True)
def no_real_embeddings(monkeypatch):
    """
    Replace the vector-store calls that would otherwise hit the real
    Gemini embeddings API with fakes, so upload tests run offline and
    fast. Each call returns a couple of made-up chunk ids.
    """
    calls = {"add": [], "delete": []}

    def fake_add_documents(user_id, documents):
        ids = [f"chunk-{len(calls['add'])}-{i}" for i in range(len(documents) or 1)]
        calls["add"].append((user_id, ids))
        return len(ids), ids

    def fake_delete_documents(user_id, chunk_ids):
        calls["delete"].append((user_id, chunk_ids))

    monkeypatch.setattr(vectorstore_service, "add_documents", fake_add_documents)
    monkeypatch.setattr(vectorstore_service, "delete_documents", fake_delete_documents)
    return calls


def test_unsupported_extension_rejected(auth_headers_factory, client):
    headers = auth_headers_factory("upload_ext_user")
    resp = client.post(
        "/upload",
        headers=headers,
        files={"file": ("malware.exe", io.BytesIO(b"not a real doc"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_oversized_upload_rejected(auth_headers_factory, client):
    # MAX_UPLOAD_SIZE_MB=1 in the test environment (see conftest.py).
    headers = auth_headers_factory("upload_size_user")
    too_big = b"x" * (2 * 1024 * 1024)
    resp = client.post(
        "/upload",
        headers=headers,
        files={"file": ("big.txt", io.BytesIO(too_big), "text/plain")},
    )
    assert resp.status_code == 413


def test_valid_upload_succeeds(auth_headers_factory, client):
    headers = auth_headers_factory("upload_ok_user")
    resp = client.post(
        "/upload",
        headers=headers,
        files={"file": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "notes.txt"
    assert body["chunks_indexed"] >= 1


def test_reupload_removes_stale_chunks_before_adding_new(auth_headers_factory, client, no_real_embeddings):
    headers = auth_headers_factory("upload_reup_user")

    resp1 = client.post(
        "/upload",
        headers=headers,
        files={"file": ("notes.txt", io.BytesIO(b"version one"), "text/plain")},
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        "/upload",
        headers=headers,
        files={"file": ("notes.txt", io.BytesIO(b"version two, totally different content"), "text/plain")},
    )
    assert resp2.status_code == 200

    # The old chunk ids from the first upload must have been deleted
    # before the second upload's chunks were added - otherwise both
    # versions would sit in the vector store at once.
    assert len(no_real_embeddings["delete"]) == 1
    deleted_user_id, deleted_ids = no_real_embeddings["delete"][0]
    first_added_ids = no_real_embeddings["add"][0][1]
    assert deleted_ids == first_added_ids


def test_identical_reupload_skips_reindexing(auth_headers_factory, client, no_real_embeddings):
    headers = auth_headers_factory("upload_dedup_user")
    payload = {"file": ("same.txt", io.BytesIO(b"unchanged content"), "text/plain")}

    resp1 = client.post("/upload", headers=headers, files=payload)
    assert resp1.status_code == 200

    payload_again = {"file": ("same.txt", io.BytesIO(b"unchanged content"), "text/plain")}
    resp2 = client.post("/upload", headers=headers, files=payload_again)
    assert resp2.status_code == 200
    assert "already indexed" in resp2.json()["message"]

    # Only the first upload should have actually called add_documents.
    assert len(no_real_embeddings["add"]) == 1
