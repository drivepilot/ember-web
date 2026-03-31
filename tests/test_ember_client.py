"""Tests for the Ember HTTP API client."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from ember_client import (
    EmberClient,
    EmberAuthError,
    EmberAPIError,
    _parse_zone,
    _get_point_value,
)
from models import ZoneMode


class TestParseZone:
    """Tests for the _parse_zone helper."""

    def test_parse_basic_zone(self):
        raw = {
            "zoneId": "z1",
            "name": "Living Room",
            "mac": "AA:BB:CC",
            "pointDataList": [
                {"pointIndex": 5, "value": "195"},
                {"pointIndex": 6, "value": "210"},
                {"pointIndex": 7, "value": "0"},
                {"pointIndex": 8, "value": "0"},
                {"pointIndex": 10, "value": "2"},
                {"pointIndex": 14, "value": "220"},
                {"pointIndex": 4, "value": "0"},
            ],
            "deviceDays": [],
        }
        zone = _parse_zone(raw)
        assert zone.name == "Living Room"
        assert zone.current_temp == 19.5
        assert zone.target_temp == 21.0
        assert zone.mode == ZoneMode.AUTO
        assert zone.boiler_on is True
        assert zone.boost_active is False
        assert zone.boost_temp == 22.0

    def test_parse_zone_with_boost(self):
        raw = {
            "name": "Bedroom",
            "mac": "DD:EE:FF",
            "pointDataList": [
                {"pointIndex": 5, "value": "180"},
                {"pointIndex": 6, "value": "190"},
                {"pointIndex": 7, "value": "2"},    # ON
                {"pointIndex": 8, "value": "2"},     # 2 hours boost
                {"pointIndex": 10, "value": "1"},
                {"pointIndex": 14, "value": "230"},
                {"pointIndex": 4, "value": "0"},
            ],
            "deviceDays": [],
        }
        zone = _parse_zone(raw)
        assert zone.boost_active is True
        assert zone.boost_hours == 2
        assert zone.boost_temp == 23.0
        assert zone.mode == ZoneMode.ON
        assert zone.is_active is True

    def test_parse_zone_with_schedule(self):
        raw = {
            "name": "Kitchen",
            "mac": "11:22:33",
            "pointDataList": [
                {"pointIndex": 5, "value": "200"},
                {"pointIndex": 6, "value": "200"},
                {"pointIndex": 7, "value": "3"},
                {"pointIndex": 8, "value": "0"},
                {"pointIndex": 10, "value": "1"},
                {"pointIndex": 14, "value": "200"},
                {"pointIndex": 4, "value": "0"},
            ],
            "deviceDays": [
                {
                    "dayType": 1,
                    "p1": {"startTime": 73, "endTime": 93},
                    "p2": {"startTime": 123, "endTime": 143},
                    "p3": {"startTime": 173, "endTime": 223},
                },
                {
                    "dayType": 2,
                    "p1": {"startTime": 73, "endTime": 93},
                    "p2": {"startTime": 0, "endTime": 0},
                    "p3": {"startTime": 0, "endTime": 0},
                },
            ],
        }
        zone = _parse_zone(raw)
        assert len(zone.schedule) == 2
        assert zone.schedule[0].day_type == 1
        assert zone.schedule[0].p1.start_time == 73

    def test_parse_zone_missing_points(self):
        """Zone with no point data should use defaults."""
        raw = {
            "name": "Empty",
            "mac": "00:00:00",
            "pointDataList": [],
            "deviceDays": [],
        }
        zone = _parse_zone(raw)
        assert zone.current_temp == 0.0
        assert zone.target_temp == 0.0
        assert zone.mode == ZoneMode.OFF

    def test_parse_zone_advance_active(self):
        raw = {
            "name": "Hall",
            "mac": "44:55:66",
            "pointDataList": [
                {"pointIndex": 4, "value": "1"},  # advance active
                {"pointIndex": 5, "value": "190"},
                {"pointIndex": 6, "value": "200"},
                {"pointIndex": 7, "value": "0"},
                {"pointIndex": 8, "value": "0"},
                {"pointIndex": 10, "value": "1"},
                {"pointIndex": 14, "value": "200"},
            ],
            "deviceDays": [],
        }
        zone = _parse_zone(raw)
        assert zone.advance_active is True
        assert zone.is_active is True


class TestGetPointValue:
    def test_existing_index(self):
        zone = {
            "pointDataList": [
                {"pointIndex": 5, "value": "195"},
                {"pointIndex": 6, "value": "210"},
            ]
        }
        assert _get_point_value(zone, 5) == 195
        assert _get_point_value(zone, 6) == 210

    def test_missing_index(self):
        zone = {"pointDataList": [{"pointIndex": 5, "value": "195"}]}
        assert _get_point_value(zone, 99) is None

    def test_empty_point_data(self):
        zone = {"pointDataList": []}
        assert _get_point_value(zone, 5) is None


class TestEmberClient:
    @pytest_asyncio.fixture
    async def client(self):
        c = EmberClient()
        yield c
        await c.close()

    @pytest.mark.asyncio
    async def test_login_success(self, client, sample_login_response):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = sample_login_response

        with patch.object(client._http, "post", AsyncMock(return_value=mock_response)):
            result = await client.login("test@example.com", "pass123")
            assert result is True
            assert client.is_logged_in is True

    @pytest.mark.asyncio
    async def test_login_failure(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"status": 1, "message": "Invalid credentials"}

        with patch.object(client._http, "post", AsyncMock(return_value=mock_response)):
            with pytest.raises(EmberAuthError, match="Invalid credentials"):
                await client.login("bad@example.com", "wrong")

    @pytest.mark.asyncio
    async def test_not_logged_in(self, client):
        assert client.is_logged_in is False
        with pytest.raises(EmberAuthError, match="Not logged in"):
            await client._ensure_token()

    @pytest.mark.asyncio
    async def test_list_homes(self, client, sample_login_response, sample_homes_response):
        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.raise_for_status = MagicMock()
        login_resp.json.return_value = sample_login_response

        homes_resp = MagicMock()
        homes_resp.status_code = 200
        homes_resp.raise_for_status = MagicMock()
        homes_resp.json.return_value = sample_homes_response

        with patch.object(client._http, "post", AsyncMock(return_value=login_resp)):
            await client.login("test@example.com", "pass")

        with patch.object(client._http, "get", AsyncMock(return_value=homes_resp)):
            homes = await client.list_homes()
            assert len(homes) == 1
            assert homes[0]["gatewayid"] == "GW-001"

    @pytest.mark.asyncio
    async def test_get_zones(self, client, sample_login_response, sample_zone_data):
        login_resp = MagicMock()
        login_resp.status_code = 200
        login_resp.raise_for_status = MagicMock()
        login_resp.json.return_value = sample_login_response

        with patch.object(client._http, "post", AsyncMock(return_value=login_resp)):
            await client.login("test@example.com", "pass")

        homes_resp = MagicMock()
        homes_resp.status_code = 200
        homes_resp.raise_for_status = MagicMock()
        homes_resp.json.return_value = {
            "status": 0,
            "data": [{"gatewayid": "GW-001"}],
        }

        zones_resp = MagicMock()
        zones_resp.status_code = 200
        zones_resp.raise_for_status = MagicMock()
        zones_resp.json.return_value = sample_zone_data

        with patch.object(client._http, "get", AsyncMock(return_value=homes_resp)):
            with patch.object(client._http, "post", AsyncMock(return_value=zones_resp)):
                zones = await client.get_zones()
                assert len(zones) == 2
                assert zones[0].name == "Living Room"
                assert zones[0].current_temp == 19.5
                assert zones[1].name == "Bedroom"
                assert zones[1].mode == ZoneMode.OFF
