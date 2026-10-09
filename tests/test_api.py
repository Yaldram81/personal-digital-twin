"""Tests for the FastAPI app: /health and debug round-trip endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from pdt.api.app import create_app, reset_state
from pdt.core.config import Settings
from pdt.memory.structured import DuckDBStructuredStore


@pytest.fixture
def client(settings: Settings, vault, tmp_data_dir):
    """A test client with an attached, unlocked store."""
    reset_state()
    app = create_app(settings)
    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    from pdt.api.app import get_state

    get_state().attach_store(store)
    with TestClient(app) as c:
        yield c
    store.close()
    reset_state()


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.0.1"
        assert data["env"] == "dev"

    def test_health_reports_vault_exists(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.json()["vault_exists"] is True


class TestWebNarrationUI:
    """Phase 1 deliverable: `ui/web/narration` -- an actual served UI, not
    just a reserved empty package.
    """

    def test_narration_ui_is_served(self, client: TestClient) -> None:
        resp = client.get("/ui/narration/")
        assert resp.status_code == 200
        assert "narration" in resp.text.lower()
        assert "/narration/start" in resp.text

    def test_main_web_ui_is_served(self, client: TestClient) -> None:
        resp = client.get("/ui/")
        assert resp.status_code == 200
        assert "personal digital twin" in resp.text.lower()
        assert "executive pulse" in resp.text.lower()
        assert "twin sandbox" in resp.text.lower()

    def test_root_redirects_to_ui(self, client: TestClient) -> None:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == "/ui/"

    def test_web_ui_assets_served(self, client: TestClient) -> None:
        resp_css = client.get("/ui/styles.css")
        assert resp_css.status_code == 200
        resp_js = client.get("/ui/app.js")
        assert resp_js.status_code == 200
        resp_graph = client.get("/ui/graph.js")
        assert resp_graph.status_code == 200


class TestDebugStoreRoundTrip:
    """Exit criterion: a round-trip store endpoint works end to end."""

    def test_write_then_read(self, client: TestClient) -> None:
        trace = json.dumps(
            {
                "id": "trace-api-001",
                "domain": "career",
                "chosen_option": "startup",
            }
        )
        write_resp = client.post("/debug/store", json={"trace_json": trace})
        assert write_resp.status_code == 200
        row_id = write_resp.json()["id"]

        read_resp = client.get(f"/debug/store/{row_id}")
        assert read_resp.status_code == 200
        retrieved = json.loads(read_resp.json()["trace_json"])
        assert retrieved["chosen_option"] == "startup"

    def test_read_nonexistent_404(self, client: TestClient) -> None:
        resp = client.get("/debug/store/does-not-exist")
        assert resp.status_code == 404
