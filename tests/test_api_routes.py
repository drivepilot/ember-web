"""Integration tests for FastAPI routes."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from models import Zone, ZoneMode


@pytest.mark.asyncio
async def test_status_not_logged_in(client):
    resp = await client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["logged_in"] is False


@pytest.mark.asyncio
async def test_zones_requires_auth(client):
    resp = await client.get("/api/zones")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_homes_requires_auth(client):
    resp = await client.get("/api/homes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_set_temperature_requires_auth(client):
    resp = await client.post(
        "/api/zones/Living%20Room/temperature",
        json={"temperature": 21.0},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_set_mode_requires_auth(client):
    resp = await client.post(
        "/api/zones/Living%20Room/mode",
        json={"mode": 0},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_boost_requires_auth(client):
    resp = await client.post(
        "/api/zones/Living%20Room/boost",
        json={"hours": 1},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_success(client, sample_login_response, sample_user_response, sample_home_details_response):
    import app as app_module

    mock_ember = AsyncMock()
    mock_ember.login = AsyncMock(return_value=True)
    mock_ember.is_logged_in = True
    mock_ember.refresh_token = "test-refresh-token"
    mock_ember.get_user_id = AsyncMock(return_value="12345")
    mock_ember.get_home_details = AsyncMock(return_value={
        "homes": {"productId": "PROD-1", "uid": "UID-1"}
    })

    mock_mqtt = MagicMock()
    mock_mqtt.configure = MagicMock()
    mock_mqtt.connect = MagicMock()

    original_ember = app_module.ember
    original_mqtt = app_module.mqtt_client
    app_module.ember = mock_ember
    app_module.mqtt_client = mock_mqtt

    try:
        resp = await client.post("/api/login", json={
            "username": "test@example.com",
            "password": "pass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
    finally:
        app_module.ember = original_ember
        app_module.mqtt_client = original_mqtt


@pytest.mark.asyncio
async def test_login_bad_credentials(client):
    import app as app_module
    from ember_client import EmberAuthError

    mock_ember = AsyncMock()
    mock_ember.login = AsyncMock(side_effect=EmberAuthError("Invalid credentials"))

    original_ember = app_module.ember
    app_module.ember = mock_ember

    try:
        resp = await client.post("/api/login", json={
            "username": "bad@example.com",
            "password": "wrong",
        })
        assert resp.status_code == 401
    finally:
        app_module.ember = original_ember


@pytest.mark.asyncio
async def test_get_zones_authenticated(client):
    import app as app_module

    zones = [
        Zone(
            zone_id="z1",
            name="Living Room",
            mac="AA:BB:CC",
            current_temp=19.5,
            target_temp=21.0,
            mode=ZoneMode.AUTO,
        ),
    ]

    mock_ember = AsyncMock()
    mock_ember.is_logged_in = True
    mock_ember.get_zones = AsyncMock(return_value=zones)

    original_ember = app_module.ember
    app_module.ember = mock_ember

    try:
        resp = await client.get("/api/zones")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Living Room"
        assert data[0]["current_temp"] == 19.5
    finally:
        app_module.ember = original_ember


@pytest.mark.asyncio
async def test_set_temperature_success(client):
    import app as app_module

    zones = [
        Zone(
            zone_id="z1",
            name="Living Room",
            mac="AA:BB:CC",
            current_temp=19.5,
            target_temp=21.0,
            mode=ZoneMode.AUTO,
        ),
    ]

    mock_ember = AsyncMock()
    mock_ember.is_logged_in = True
    mock_ember.get_zones = AsyncMock(return_value=zones)

    mock_mqtt = MagicMock()
    mock_mqtt.is_connected = True
    mock_mqtt.set_target_temperature = MagicMock(return_value=True)

    original_ember = app_module.ember
    original_mqtt = app_module.mqtt_client
    app_module.ember = mock_ember
    app_module.mqtt_client = mock_mqtt

    try:
        resp = await client.post(
            "/api/zones/Living%20Room/temperature",
            json={"temperature": 22.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["target_temp"] == 22.0
        mock_mqtt.set_target_temperature.assert_called_once_with("AA:BB:CC", 22.0)
    finally:
        app_module.ember = original_ember
        app_module.mqtt_client = original_mqtt


@pytest.mark.asyncio
async def test_set_mode_success(client):
    import app as app_module

    zones = [
        Zone(zone_id="z1", name="Living Room", mac="AA:BB:CC", mode=ZoneMode.AUTO),
    ]

    mock_ember = AsyncMock()
    mock_ember.is_logged_in = True
    mock_ember.get_zones = AsyncMock(return_value=zones)

    mock_mqtt = MagicMock()
    mock_mqtt.is_connected = True
    mock_mqtt.set_mode = MagicMock(return_value=True)

    original_ember = app_module.ember
    original_mqtt = app_module.mqtt_client
    app_module.ember = mock_ember
    app_module.mqtt_client = mock_mqtt

    try:
        resp = await client.post(
            "/api/zones/Living%20Room/mode",
            json={"mode": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["mode"] == "OFF"
        mock_mqtt.set_mode.assert_called_once_with("AA:BB:CC", 3)
    finally:
        app_module.ember = original_ember
        app_module.mqtt_client = original_mqtt


@pytest.mark.asyncio
async def test_zone_not_found(client):
    import app as app_module

    mock_ember = AsyncMock()
    mock_ember.is_logged_in = True
    mock_ember.get_zones = AsyncMock(return_value=[])

    mock_mqtt = MagicMock()
    mock_mqtt.is_connected = True

    original_ember = app_module.ember
    original_mqtt = app_module.mqtt_client
    app_module.ember = mock_ember
    app_module.mqtt_client = mock_mqtt

    try:
        resp = await client.post(
            "/api/zones/Nonexistent/temperature",
            json={"temperature": 20.0},
        )
        assert resp.status_code == 404
    finally:
        app_module.ember = original_ember
        app_module.mqtt_client = original_mqtt


@pytest.mark.asyncio
async def test_invalid_temperature(client):
    import app as app_module

    mock_ember = AsyncMock()
    mock_ember.is_logged_in = True

    original_ember = app_module.ember
    app_module.ember = mock_ember

    try:
        resp = await client.post(
            "/api/zones/Living%20Room/temperature",
            json={"temperature": 50.0},  # too high
        )
        assert resp.status_code == 422  # validation error
    finally:
        app_module.ember = original_ember


@pytest.mark.asyncio
async def test_static_pages(client):
    """Test that static pages are served."""
    resp = await client.get("/")
    assert resp.status_code == 200

    resp = await client.get("/login")
    assert resp.status_code == 200
