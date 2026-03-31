"""Pydantic models for the Ember Web API."""

from enum import IntEnum
from typing import Optional
from pydantic import BaseModel, Field


class ZoneMode(IntEnum):
    AUTO = 0
    ALL_DAY = 1
    ON = 2
    OFF = 3


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str = ""


class Home(BaseModel):
    gateway_id: str = Field(alias="gatewayid")
    name: str = ""

    model_config = {"populate_by_name": True}


class SchedulePeriod(BaseModel):
    start_time: int = Field(alias="startTime", default=0)
    end_time: int = Field(alias="endTime", default=0)

    model_config = {"populate_by_name": True}


class ScheduleDay(BaseModel):
    day_type: int = Field(alias="dayType")
    p1: SchedulePeriod = SchedulePeriod(startTime=0, endTime=0)
    p2: SchedulePeriod = SchedulePeriod(startTime=0, endTime=0)
    p3: SchedulePeriod = SchedulePeriod(startTime=0, endTime=0)

    model_config = {"populate_by_name": True}


class PointData(BaseModel):
    point_index: int = Field(alias="pointIndex")
    value: str

    model_config = {"populate_by_name": True}


class Zone(BaseModel):
    zone_id: str = ""
    name: str
    mac: str = ""
    current_temp: float = 0.0
    target_temp: float = 0.0
    mode: ZoneMode = ZoneMode.OFF
    boost_active: bool = False
    boost_hours: int = 0
    boost_temp: float = 0.0
    boiler_on: bool = False
    is_active: bool = False
    advance_active: bool = False
    schedule: list[ScheduleDay] = []


class SetTemperatureRequest(BaseModel):
    temperature: float = Field(ge=5.0, le=35.0)


class SetModeRequest(BaseModel):
    mode: ZoneMode


class BoostRequest(BaseModel):
    hours: int = Field(ge=1, le=3, default=1)
    temperature: Optional[float] = Field(default=None, ge=5.0, le=35.0)


class ZoneUpdate(BaseModel):
    """Real-time zone update pushed via WebSocket."""
    zone_name: str
    current_temp: Optional[float] = None
    target_temp: Optional[float] = None
    mode: Optional[ZoneMode] = None
    boost_active: Optional[bool] = None
    boiler_on: Optional[bool] = None
