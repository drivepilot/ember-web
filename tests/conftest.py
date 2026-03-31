"""Shared test fixtures for the Ember Web test suite."""

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add backend to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app import app  # noqa: E402


@pytest.fixture
def sample_login_response():
    """Successful login response from the Ember API."""
    return {
        "status": 0,
        "message": "success",
        "data": {
            "token": "test-access-token-123",
            "refresh_token": "test-refresh-token-456",
        },
    }


@pytest.fixture
def sample_refresh_response():
    """Token refresh response."""
    return {
        "status": 0,
        "data": {
            "token": "new-access-token-789",
            "refresh_token": "new-refresh-token-012",
        },
    }


@pytest.fixture
def sample_user_response():
    """User details response."""
    return {
        "status": 0,
        "data": {
            "id": 12345,
            "email": "test@example.com",
        },
    }


@pytest.fixture
def sample_homes_response():
    """Homes list response."""
    return {
        "status": 0,
        "data": [
            {
                "gatewayid": "GW-001",
                "name": "My Home",
            }
        ],
    }


@pytest.fixture
def sample_home_details_response():
    """Home details response."""
    return {
        "status": 0,
        "data": {
            "homes": {
                "productId": "PROD-001",
                "uid": "UID-001",
                "gatewayid": "GW-001",
            }
        },
    }


@pytest.fixture
def sample_zone_data():
    """Raw zone data as returned by the Ember API."""
    return {
        "status": 0,
        "timestamp": 1700000000000,
        "data": [
            {
                "zoneId": "zone-1",
                "name": "Living Room",
                "mac": "AA:BB:CC:DD:EE:01",
                "pointDataList": [
                    {"pointIndex": 4, "value": "0"},    # ADVANCE_ACTIVE
                    {"pointIndex": 5, "value": "195"},   # CURRENT_TEMP (19.5)
                    {"pointIndex": 6, "value": "210"},   # TARGET_TEMP (21.0)
                    {"pointIndex": 7, "value": "0"},     # MODE (AUTO)
                    {"pointIndex": 8, "value": "0"},     # BOOST_HOURS
                    {"pointIndex": 9, "value": "0"},     # BOOST_TIME
                    {"pointIndex": 10, "value": "2"},    # BOILER_STATE (on)
                    {"pointIndex": 14, "value": "220"},  # BOOST_TEMP (22.0)
                ],
                "deviceDays": [
                    {
                        "dayType": 1,
                        "p1": {"startTime": 73, "endTime": 93},
                        "p2": {"startTime": 123, "endTime": 143},
                        "p3": {"startTime": 173, "endTime": 223},
                    }
                ],
            },
            {
                "zoneId": "zone-2",
                "name": "Bedroom",
                "mac": "AA:BB:CC:DD:EE:02",
                "pointDataList": [
                    {"pointIndex": 4, "value": "0"},
                    {"pointIndex": 5, "value": "180"},   # 18.0
                    {"pointIndex": 6, "value": "190"},   # 19.0
                    {"pointIndex": 7, "value": "3"},     # OFF
                    {"pointIndex": 8, "value": "0"},
                    {"pointIndex": 9, "value": "0"},
                    {"pointIndex": 10, "value": "1"},    # boiler off
                    {"pointIndex": 14, "value": "200"},
                ],
                "deviceDays": [],
            },
        ],
    }


@pytest.fixture
def sample_zones_parsed(sample_zone_data):
    """Expected parsed zone objects from sample_zone_data."""
    from models import Zone, ZoneMode, ScheduleDay, SchedulePeriod

    return [
        Zone(
            zone_id="zone-1",
            name="Living Room",
            mac="AA:BB:CC:DD:EE:01",
            current_temp=19.5,
            target_temp=21.0,
            mode=ZoneMode.AUTO,
            boost_active=False,
            boost_hours=0,
            boost_temp=22.0,
            boiler_on=True,
            is_active=False,
            advance_active=False,
            schedule=[
                ScheduleDay(
                    dayType=1,
                    p1=SchedulePeriod(startTime=73, endTime=93),
                    p2=SchedulePeriod(startTime=123, endTime=143),
                    p3=SchedulePeriod(startTime=173, endTime=223),
                )
            ],
        ),
        Zone(
            zone_id="zone-2",
            name="Bedroom",
            mac="AA:BB:CC:DD:EE:02",
            current_temp=18.0,
            target_temp=19.0,
            mode=ZoneMode.OFF,
            boost_active=False,
            boost_hours=0,
            boost_temp=20.0,
            boiler_on=False,
            is_active=False,
            advance_active=False,
            schedule=[],
        ),
    ]


@pytest_asyncio.fixture
async def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
