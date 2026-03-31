"""HTTP client for the EPH Controls Ember API.

Based on the reverse-engineered API documented at:
https://github.com/ttroy50/pyephember
"""

import datetime
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

from models import Zone, ZoneMode, ScheduleDay, SchedulePeriod


API_BASE = "https://eu-https.topband-cloud.com/ember-back/"
TOKEN_REFRESH_SECONDS = 1800  # 30 minutes


class EmberAuthError(Exception):
    pass


class EmberAPIError(Exception):
    pass


class EmberClient:
    """Async HTTP client for the Ember heating API."""

    def __init__(self):
        self._http = httpx.AsyncClient(base_url=API_BASE, timeout=15.0)
        self._token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._last_refresh: Optional[datetime.datetime] = None
        self._user_id: Optional[str] = None
        self._homes: list[dict] = []
        self._home_details: Optional[dict] = None

    async def close(self):
        await self._http.aclose()

    # --- Auth ---

    async def login(self, username: str, password: str) -> bool:
        """Login and obtain access + refresh tokens."""
        resp = await self._http.post(
            "appLogin/login",
            json={"userName": username, "password": password},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 0:
            raise EmberAuthError(data.get("message", "Login failed"))

        self._token = data["data"]["token"]
        self._refresh_token = data["data"]["refresh_token"]
        self._last_refresh = datetime.datetime.now(datetime.UTC)
        return True

    async def _ensure_token(self):
        """Refresh the token if it's about to expire."""
        if self._token is None:
            raise EmberAuthError("Not logged in")
        if self._needs_refresh():
            await self._refresh()

    def _needs_refresh(self) -> bool:
        if self._last_refresh is None:
            return True
        expires_at = self._last_refresh + datetime.timedelta(seconds=TOKEN_REFRESH_SECONDS)
        now_plus_buffer = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)
        return expires_at < now_plus_buffer

    async def _refresh(self):
        resp = await self._http.get(
            "appLogin/refreshAccessToken",
            headers={
                "Authorization": self._refresh_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if "token" not in data.get("data", {}):
            raise EmberAuthError("Token refresh failed")
        self._token = data["data"]["token"]
        self._refresh_token = data["data"]["refresh_token"]
        self._last_refresh = datetime.datetime.now(datetime.UTC)

    def _auth_headers(self) -> dict:
        return {
            "Authorization": self._token,
            "Content-Type": "application/json;charset=utf-8",
            "Accept": "application/json",
        }

    @property
    def is_logged_in(self) -> bool:
        return self._token is not None

    @property
    def access_token(self) -> Optional[str]:
        return self._token

    @property
    def refresh_token(self) -> Optional[str]:
        return self._refresh_token

    @property
    def user_id(self) -> Optional[str]:
        return self._user_id

    # --- User ---

    async def get_user_id(self) -> str:
        if self._user_id:
            return self._user_id
        await self._ensure_token()
        resp = await self._http.get("user/selectUser", headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 0:
            raise EmberAPIError("Failed to get user details")
        self._user_id = str(data["data"]["id"])
        return self._user_id

    # --- Homes ---

    async def list_homes(self) -> list[dict]:
        await self._ensure_token()
        resp = await self._http.get("homes/list", headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 0:
            raise EmberAPIError("Failed to list homes")
        self._homes = data.get("data", [])
        return self._homes

    async def get_home_details(self, gateway_id: Optional[str] = None) -> dict:
        if self._home_details:
            return self._home_details
        await self._ensure_token()
        if gateway_id is None:
            if not self._homes:
                self._homes = await self.list_homes()
            gateway_id = self._homes[0]["gatewayid"]
        resp = await self._http.post(
            "homes/detail",
            json={"gateWayId": gateway_id},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 0:
            raise EmberAPIError("Failed to get home details")
        self._home_details = data["data"]
        return self._home_details

    # --- Zones ---

    async def get_zones_raw(self, gateway_id: Optional[str] = None) -> list[dict]:
        """Get raw zone data from the API."""
        await self._ensure_token()
        if gateway_id is None:
            if not self._homes:
                self._homes = await self.list_homes()
            gateway_id = self._homes[0]["gatewayid"]
        resp = await self._http.post(
            "homesVT/zoneProgram",
            json={"gateWayId": gateway_id},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 0:
            raise EmberAPIError("Failed to get zones")
        timestamp = data.get("timestamp", int(time.time() * 1000))
        zones = data.get("data", [])
        for zone in zones:
            zone["timestamp"] = timestamp
        return zones

    async def get_zones(self, gateway_id: Optional[str] = None) -> list[Zone]:
        """Get parsed zone data."""
        raw_zones = await self.get_zones_raw(gateway_id)
        return [_parse_zone(z) for z in raw_zones]

    # --- Commands via HTTP API (API_2020 endpoints) ---

    async def set_zone_target_temperature(self, zone_id: str, temperature: float) -> bool:
        """Set target temperature for a zone via HTTP API."""
        await self._ensure_token()
        body = {"zoneid": zone_id, "temperature": temperature}  # temperature as number
        logger.info("SET TEMP request: %s", body)
        resp = await self._http.post(
            "zones/setTargetTemperature",
            json=body,
            headers=self._auth_headers(),
        )
        logger.info("SET TEMP response: status=%d body=%s", resp.status_code, resp.text)
        if resp.status_code != 200:
            resp.raise_for_status()
        data = resp.json()
        return data.get("status") == 0

    async def set_zone_mode(self, zone_id: str, mode: int) -> bool:
        """Set zone mode via HTTP API. 0=auto, 1=all_day, 2=on, 3=off."""
        await self._ensure_token()
        body = {"zoneid": zone_id, "model": str(mode)}
        logger.info("SET MODE request: %s", body)
        resp = await self._http.post(
            "zones/setModel",
            json=body,
            headers=self._auth_headers(),
        )
        logger.info("SET MODE response: status=%d body=%s", resp.status_code, resp.text)
        resp.raise_for_status()
        data = resp.json()
        return data.get("status") == 0

    async def activate_zone_boost(self, zone_id: str, hours: int = 1, temperature: Optional[float] = None) -> bool:
        """Activate boost for a zone via HTTP API."""
        await self._ensure_token()
        body = {"zoneid": zone_id, "hours": str(hours)}
        if temperature is not None:
            body["temperature"] = str(temperature)
        resp = await self._http.post(
            "zones/boost",
            json=body,
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("status") == 0

    async def cancel_zone_boost(self, zone_id: str) -> bool:
        """Cancel boost for a zone via HTTP API."""
        await self._ensure_token()
        resp = await self._http.post(
            "zones/cancelBoost",
            json={"zoneid": zone_id},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("status") == 0

    async def advance_zone(self, zone_id: str) -> bool:
        """Advance a zone via HTTP API."""
        await self._ensure_token()
        resp = await self._http.post(
            "zones/adv",
            json={"zoneid": zone_id},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("status") == 0

    async def cancel_zone_advance(self, zone_id: str) -> bool:
        """Cancel advance for a zone via HTTP API."""
        await self._ensure_token()
        resp = await self._http.post(
            "zones/cancelAdv",
            json={"zoneid": zone_id},
            headers=self._auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("status") == 0

    def get_messaging_credentials(self) -> dict:
        """Return credentials needed for MQTT connection."""
        if not self._token:
            raise EmberAuthError("Not logged in")
        return {
            "user_id": self._user_id or "",
            "token": self._token,
        }


# --- Zone parsing helpers ---

def _get_point_value(zone: dict, index: int) -> Optional[int]:
    """Extract a point data value by index from raw zone data."""
    for point in zone.get("pointDataList", []):
        if point.get("pointIndex") == index:
            return int(point["value"])
    return None


# Point data indices (from pyephember)
_IDX_ADVANCE = 4
_IDX_CURRENT_TEMP = 5
_IDX_TARGET_TEMP = 6
_IDX_MODE = 7
_IDX_BOOST_HOURS = 8
_IDX_BOOST_TIME = 9
_IDX_BOILER_STATE = 10
_IDX_BOOST_TEMP = 14


def _parse_zone(raw: dict) -> Zone:
    """Parse raw API zone data into a Zone model."""
    mode_val = _get_point_value(raw, _IDX_MODE)
    try:
        mode = ZoneMode(mode_val) if mode_val is not None else ZoneMode.OFF
    except ValueError:
        # API can return unexpected mode values (e.g. 350); default to AUTO
        mode = ZoneMode.AUTO

    current_temp_raw = _get_point_value(raw, _IDX_CURRENT_TEMP)
    current_temp = (current_temp_raw / 10.0) if current_temp_raw is not None else 0.0

    target_temp_raw = _get_point_value(raw, _IDX_TARGET_TEMP)
    target_temp = (target_temp_raw / 10.0) if target_temp_raw is not None else 0.0

    boost_hours = _get_point_value(raw, _IDX_BOOST_HOURS) or 0
    boost_temp_raw = _get_point_value(raw, _IDX_BOOST_TEMP)
    boost_temp = (boost_temp_raw / 10.0) if boost_temp_raw is not None else 0.0

    boiler_state = _get_point_value(raw, _IDX_BOILER_STATE)
    advance = _get_point_value(raw, _IDX_ADVANCE) or 0

    is_active = mode in (ZoneMode.ON, ZoneMode.ALL_DAY) or boost_hours > 0 or advance != 0

    schedule = []
    for day in raw.get("deviceDays", []):
        schedule.append(ScheduleDay(
            dayType=day.get("dayType", 0),
            p1=SchedulePeriod(
                startTime=day.get("p1", {}).get("startTime", 0),
                endTime=day.get("p1", {}).get("endTime", 0),
            ),
            p2=SchedulePeriod(
                startTime=day.get("p2", {}).get("startTime", 0),
                endTime=day.get("p2", {}).get("endTime", 0),
            ),
            p3=SchedulePeriod(
                startTime=day.get("p3", {}).get("startTime", 0),
                endTime=day.get("p3", {}).get("endTime", 0),
            ),
        ))

    return Zone(
        zone_id=str(raw.get("zoneid", raw.get("zoneId", raw.get("id", "")))),
        name=raw.get("name", "Unknown"),
        mac=raw.get("mac", ""),
        current_temp=current_temp,
        target_temp=target_temp,
        mode=mode,
        boost_active=boost_hours > 0,
        boost_hours=boost_hours,
        boost_temp=boost_temp,
        boiler_on=(boiler_state == 2),
        is_active=is_active,
        advance_active=(advance != 0),
        schedule=schedule,
    )
