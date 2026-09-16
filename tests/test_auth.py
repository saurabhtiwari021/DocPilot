def test_register_new_user(client):
    resp = client.post("/auth/register", json={"username": "alice_auth", "password": "password123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice_auth"
    assert "id" in body


def test_register_duplicate_username_rejected(client):
    client.post("/auth/register", json={"username": "bob_auth", "password": "password123"})
    resp = client.post("/auth/register", json={"username": "bob_auth", "password": "password123"})
    assert resp.status_code == 400


def test_login_wrong_password_rejected(client):
    client.post("/auth/register", json={"username": "carol_auth", "password": "password123"})
    resp = client.post("/auth/login", data={"username": "carol_auth", "password": "wrong-password"})
    assert resp.status_code == 401


def test_login_success_returns_bearer_token(client):
    client.post("/auth/register", json={"username": "dave_auth", "password": "password123"})
    resp = client.post("/auth/login", data={"username": "dave_auth", "password": "password123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_protected_route_without_token_rejected(client):
    resp = client.get("/documents")
    assert resp.status_code == 401


def test_protected_route_with_garbage_token_rejected(client):
    resp = client.get("/documents", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


def test_protected_route_with_valid_token_succeeds(auth_headers_factory, client):
    headers = auth_headers_factory("erin_auth")
    resp = client.get("/documents", headers=headers)
    assert resp.status_code == 200
