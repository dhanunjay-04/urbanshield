import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app

client = TestClient(app)


def test_root_serves_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="assistantToggle"' in response.text


def test_health_reports_loaded_assets():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["asset_count"] == 2500


def test_dashboard_page_is_served():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "UrbanShield" in response.text
    assert 'id="assistantToggle"' in response.text
    assert 'id="apiDocsLink"' in response.text


def test_assistant_page_is_served():
    response = client.get("/ai_assistant/chat.html")
    assert response.status_code == 200
    assert "UrbanShield AI Assistant" in response.text
    assert "assistant=1" in response.text


def test_single_service_assistant_returns_live_data():
    response = client.post(
        "/assistant-api/ask",
        json={"question": "Summarize city risk"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "Total assets: 2500" in response.json()["answer"]


def test_api_prefix_supports_hosted_dashboard_requests():
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.json()["total_assets"] == 2500


def test_stats_has_risk_summary():
    response = client.get("/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_assets"] == 2500
    assert body["critical_count"] > 0


def test_nearby_includes_distance():
    response = client.get("/nearby", params={"lat": 17.25, "lon": 80.15, "radius_m": 500})
    assert response.status_code == 200
    assets = response.json()
    assert assets
    assert "distance_m" in assets[0]
    assert assets[0]["distance_m"] <= 500


def test_invalid_grid_size_is_rejected():
    response = client.get("/hotspots", params={"grid_size": 0})
    assert response.status_code == 422


def test_missing_asset_returns_404():
    response = client.get("/assets/DOES-NOT-EXIST")
    assert response.status_code == 404
