from fastapi.testclient import TestClient
from documouse.main import create_app


def test_auth_middleware_disabled_by_default(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    res = client.get("/api/documents")
    assert res.status_code == 200


def test_auth_middleware_enforced_when_token_configured(monkeypatch, tmp_path):
    secret = "secret-token-12345"
    monkeypatch.setenv("DOCUMOUSE_AUTH_TOKEN", secret)
    monkeypatch.setenv("DOCUMOUSE_DATABASE_URL", f"sqlite:///{tmp_path / 'auth_test.db'}")
    monkeypatch.setenv("DOCUMOUSE_STORAGE_DIR", str(tmp_path / "data"))

    from documouse import config, db
    config.get_settings.cache_clear()
    db.init_engine()

    with TestClient(create_app()) as client:
        # Health endpoint is public
        res = client.get("/api/health")
        assert res.status_code == 200

        # Protected endpoints require auth
        res = client.get("/api/documents")
        assert res.status_code == 401

        res = client.get("/api/documents", headers={"Authorization": "Bearer wrong-token"})
        assert res.status_code == 401

        res = client.get("/api/documents", headers={"Authorization": f"Bearer {secret}"})
        assert res.status_code == 200

        # CORS preflight options bypass auth
        res = client.options(
            "/api/documents",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert "access-control-allow-origin" in res.headers

    config.get_settings.cache_clear()
