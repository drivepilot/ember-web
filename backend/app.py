"""FastAPI server for the Ember Web Dashboard.

Proxies requests to the Ember cloud API and bridges MQTT updates
to browser WebSocket connections.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ember_client import EmberClient, EmberAuthError, EmberAPIError
from mqtt_client import EmberMQTTClient, ZoneCommand
from models import (
    LoginRequest,
    LoginResponse,
    SetTemperatureRequest,
    SetModeRequest,
    BoostRequest,
    Zone,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Global state
ember: Optional[EmberClient] = None
mqtt_client: Optional[EmberMQTTClient] = None
ws_connections: list[WebSocket] = []
_event_loop: Optional[asyncio.AbstractEventLoop] = None

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ember, mqtt_client, _event_loop
    _event_loop = asyncio.get_running_loop()
    ember = EmberClient()
    mqtt_client = EmberMQTTClient()
    yield
    if mqtt_client:
        mqtt_client.disconnect()
    if ember:
        await ember.close()


app = FastAPI(title="Ember Web Dashboard", lifespan=lifespan)


# --- WebSocket broadcasting ---

async def broadcast_update(data: dict):
    """Send an update to all connected WebSocket clients."""
    message = json.dumps(data)
    disconnected = []
    for ws in ws_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ws_connections.remove(ws)


def on_mqtt_zone_update(payload: dict):
    """Called by the MQTT client thread — schedule coroutine on the main loop."""
    if _event_loop is not None and _event_loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast_update(payload), _event_loop)


# --- Auth routes ---

@app.post("/api/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    try:
        await ember.login(req.username, req.password)

        # Set up MQTT after successful login
        user_id = await ember.get_user_id()
        home_details = await ember.get_home_details()
        home = home_details.get("homes", {})

        mqtt_client.configure(
            user_id=user_id,
            token=ember.access_token,
            product_id=home.get("productId", ""),
            uid=home.get("uid", ""),
            on_zone_update=on_mqtt_zone_update,
        )
        try:
            mqtt_client.connect()
        except Exception:
            logger.warning("MQTT connection failed, real-time updates unavailable")

        return LoginResponse(success=True, message="Logged in")
    except EmberAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception("Login error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status")
async def auth_status():
    return {
        "logged_in": ember.is_logged_in if ember else False,
        "mqtt_connected": mqtt_client.is_connected if mqtt_client else False,
    }


# --- Home routes ---

@app.get("/api/homes")
async def list_homes():
    _require_auth()
    try:
        homes = await ember.list_homes()
        return {"homes": homes}
    except EmberAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


# --- Zone routes ---

@app.get("/api/zones", response_model=list[Zone])
async def get_zones():
    _require_auth()
    try:
        return await ember.get_zones()
    except EmberAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/zones/{zone_name}/temperature")
async def set_temperature(zone_name: str, req: SetTemperatureRequest):
    _require_auth()
    _require_mqtt()
    zone = await _find_zone(zone_name)
    logger.info("SET TEMP: zone=%s mac=%s temp=%.1f mqtt_connected=%s",
                zone.name, zone.mac, req.temperature, mqtt_client.is_connected)
    try:
        success = mqtt_client.set_target_temperature(zone.mac, req.temperature)
        logger.info("SET TEMP result: success=%s", success)
        if not success:
            raise HTTPException(status_code=500, detail="MQTT command failed")
        return {"success": True, "zone": zone_name, "target_temp": req.temperature}
    except Exception as e:
        logger.exception("Failed to set temperature")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/zones/{zone_name}/mode")
async def set_mode(zone_name: str, req: SetModeRequest):
    _require_auth()
    _require_mqtt()
    zone = await _find_zone(zone_name)
    try:
        success = mqtt_client.set_mode(zone.mac, req.mode.value)
        if not success:
            raise HTTPException(status_code=500, detail="MQTT command failed")
        return {"success": True, "zone": zone_name, "mode": req.mode.name}
    except Exception as e:
        logger.exception("Failed to set mode")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/zones/{zone_name}/boost")
async def activate_boost(zone_name: str, req: BoostRequest):
    _require_auth()
    _require_mqtt()
    zone = await _find_zone(zone_name)
    try:
        success = mqtt_client.activate_boost(zone.mac, req.hours, req.temperature)
        if not success:
            raise HTTPException(status_code=500, detail="MQTT command failed")
        return {"success": True, "zone": zone_name, "boost_hours": req.hours}
    except Exception as e:
        logger.exception("Failed to activate boost")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/zones/{zone_name}/boost/cancel")
async def cancel_boost(zone_name: str):
    _require_auth()
    _require_mqtt()
    zone = await _find_zone(zone_name)
    try:
        success = mqtt_client.deactivate_boost(zone.mac)
        if not success:
            raise HTTPException(status_code=500, detail="MQTT command failed")
        return {"success": True, "zone": zone_name}
    except Exception as e:
        logger.exception("Failed to cancel boost")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/zones/{zone_name}/advance")
async def toggle_advance(zone_name: str):
    _require_auth()
    _require_mqtt()
    zone = await _find_zone(zone_name)
    new_state = not zone.advance_active
    try:
        success = mqtt_client.set_advance(zone.mac, active=new_state)
        if not success:
            raise HTTPException(status_code=500, detail="MQTT command failed")
        return {"success": True, "zone": zone_name, "advance_active": new_state}
    except Exception as e:
        logger.exception("Failed to toggle advance")
        raise HTTPException(status_code=500, detail=str(e))


# --- WebSocket ---

@app.websocket("/ws/updates")
async def websocket_updates(websocket: WebSocket):
    await websocket.accept()
    ws_connections.append(websocket)
    try:
        while True:
            # Keep connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in ws_connections:
            ws_connections.remove(websocket)


# --- Static files (frontend) ---

@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/login")
async def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")


# Mount static assets after explicit routes
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


# --- Helpers ---

def _require_auth():
    if not ember or not ember.is_logged_in:
        raise HTTPException(status_code=401, detail="Not logged in")


def _require_mqtt():
    if not mqtt_client or not mqtt_client.is_connected:
        raise HTTPException(status_code=503, detail="MQTT not connected — real-time control unavailable")


async def _find_zone(zone_name: str) -> Zone:
    zones = await ember.get_zones()
    for z in zones:
        if z.name == zone_name:
            return z
    raise HTTPException(status_code=404, detail=f"Zone '{zone_name}' not found")
