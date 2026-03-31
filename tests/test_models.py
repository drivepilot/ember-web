"""Tests for Pydantic models."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from models import (
    Zone,
    ZoneMode,
    LoginRequest,
    SetTemperatureRequest,
    SetModeRequest,
    BoostRequest,
    ScheduleDay,
    SchedulePeriod,
    ZoneUpdate,
)


class TestZoneMode:
    def test_mode_values(self):
        assert ZoneMode.AUTO == 0
        assert ZoneMode.ALL_DAY == 1
        assert ZoneMode.ON == 2
        assert ZoneMode.OFF == 3

    def test_mode_from_int(self):
        assert ZoneMode(0) == ZoneMode.AUTO
        assert ZoneMode(3) == ZoneMode.OFF


class TestLoginRequest:
    def test_valid(self):
        req = LoginRequest(username="test@example.com", password="pass123")
        assert req.username == "test@example.com"
        assert req.password == "pass123"

    def test_missing_fields(self):
        with pytest.raises(Exception):
            LoginRequest()


class TestSetTemperatureRequest:
    def test_valid(self):
        req = SetTemperatureRequest(temperature=21.5)
        assert req.temperature == 21.5

    def test_min_temperature(self):
        with pytest.raises(Exception):
            SetTemperatureRequest(temperature=4.0)

    def test_max_temperature(self):
        with pytest.raises(Exception):
            SetTemperatureRequest(temperature=36.0)

    def test_boundary_values(self):
        req_min = SetTemperatureRequest(temperature=5.0)
        req_max = SetTemperatureRequest(temperature=35.0)
        assert req_min.temperature == 5.0
        assert req_max.temperature == 35.0


class TestSetModeRequest:
    def test_valid(self):
        req = SetModeRequest(mode=ZoneMode.AUTO)
        assert req.mode == ZoneMode.AUTO

    def test_from_int(self):
        req = SetModeRequest(mode=2)
        assert req.mode == ZoneMode.ON


class TestBoostRequest:
    def test_defaults(self):
        req = BoostRequest()
        assert req.hours == 1
        assert req.temperature is None

    def test_with_temperature(self):
        req = BoostRequest(hours=2, temperature=22.0)
        assert req.hours == 2
        assert req.temperature == 22.0

    def test_invalid_hours(self):
        with pytest.raises(Exception):
            BoostRequest(hours=4)

    def test_invalid_hours_zero(self):
        with pytest.raises(Exception):
            BoostRequest(hours=0)


class TestSchedulePeriod:
    def test_from_alias(self):
        sp = SchedulePeriod(startTime=73, endTime=93)
        assert sp.start_time == 73
        assert sp.end_time == 93

    def test_defaults(self):
        sp = SchedulePeriod(startTime=0, endTime=0)
        assert sp.start_time == 0


class TestScheduleDay:
    def test_from_alias(self):
        day = ScheduleDay(
            dayType=1,
            p1=SchedulePeriod(startTime=73, endTime=93),
            p2=SchedulePeriod(startTime=0, endTime=0),
            p3=SchedulePeriod(startTime=0, endTime=0),
        )
        assert day.day_type == 1


class TestZone:
    def test_create(self):
        zone = Zone(
            zone_id="z1",
            name="Living Room",
            mac="AA:BB:CC",
            current_temp=19.5,
            target_temp=21.0,
            mode=ZoneMode.AUTO,
        )
        assert zone.name == "Living Room"
        assert zone.current_temp == 19.5
        assert zone.mode == ZoneMode.AUTO
        assert zone.boost_active is False

    def test_defaults(self):
        zone = Zone(name="Test")
        assert zone.zone_id == ""
        assert zone.current_temp == 0.0
        assert zone.mode == ZoneMode.OFF
        assert zone.schedule == []


class TestZoneUpdate:
    def test_partial_update(self):
        update = ZoneUpdate(zone_name="Living Room", current_temp=20.5)
        assert update.zone_name == "Living Room"
        assert update.current_temp == 20.5
        assert update.target_temp is None
        assert update.mode is None
