"""MQTT client for real-time Ember zone updates and commands.

Connects to the Topband MQTT broker to:
- Receive real-time zone point data updates
- Send commands (temperature, mode, boost) to zones
"""

import asyncio
import base64
import json
import logging
import ssl
import time
from typing import Callable, Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

MQTT_HOST = "eu-base-mqtt.topband-cloud.com"
MQTT_PORT = 18883


class ZoneCommand:
    """A command to write to a zone via MQTT."""

    # Type definitions: id, byte_length
    TYPES = {
        "SMALL_INT": (1, 1),
        "TEMP_RO": (2, 2),
        "TEMP_RW": (4, 2),
        "TIMESTAMP": (5, 4),
    }

    # Command name -> type name
    WRITABLE = {
        "ADVANCE_ACTIVE": "SMALL_INT",   # index 4
        "TARGET_TEMP": "TEMP_RW",        # index 6
        "MODE": "SMALL_INT",             # index 7
        "BOOST_HOURS": "SMALL_INT",      # index 8
        "BOOST_TIME": "TIMESTAMP",       # index 9
        "BOOST_TEMP": "TEMP_RW",         # index 14
    }

    # Command name -> point index
    INDICES = {
        "ADVANCE_ACTIVE": 4,
        "TARGET_TEMP": 6,
        "MODE": 7,
        "BOOST_HOURS": 8,
        "BOOST_TIME": 9,
        "BOOST_TEMP": 14,
    }

    def __init__(self, name: str, value):
        if name not in self.WRITABLE:
            raise ValueError(f"Cannot write to read-only value {name}")
        self.name = name
        self.value = value

    def to_ints(self) -> list[int]:
        """Convert this command to an array of integers for MQTT transmission."""
        type_name = self.WRITABLE[self.name]
        type_id, byte_len = self.TYPES[type_name]
        index = self.INDICES[self.name]

        int_array = [0, index, type_id]

        send_value = self.value
        if type_name == "TEMP_RW":
            send_value = int(10 * send_value)
        elif type_name == "TIMESTAMP":
            if hasattr(send_value, "timestamp"):
                send_value = int(send_value.timestamp())

        for b in send_value.to_bytes(byte_len, "big"):
            int_array.append(int(b))

        return int_array


def commands_to_base64(commands: list[ZoneCommand]) -> str:
    """Encode a list of ZoneCommands as a base64 string."""
    ints = []
    for cmd in commands:
        ints.extend(cmd.to_ints())
    return base64.b64encode(bytes(ints)).decode("ascii")


class EmberMQTTClient:
    """Manages the MQTT connection to the Ember broker."""

    def __init__(self):
        self._client: Optional[mqtt.Client] = None
        self._product_id: Optional[str] = None
        self._uid: Optional[str] = None
        self._user_id: Optional[str] = None
        self._on_zone_update: Optional[Callable] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def configure(
        self,
        user_id: str,
        token: str,
        product_id: str,
        uid: str,
        on_zone_update: Optional[Callable] = None,
    ):
        """Configure and connect the MQTT client."""
        self._product_id = product_id
        self._uid = uid
        self._user_id = user_id
        self._on_zone_update = on_zone_update

        client_id = f"{user_id}_{int(time.time() * 1000)}"
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

        username = f"app/{token}"
        self._client.username_pw_set(username, token)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def connect(self):
        """Connect and start the network loop in a background thread."""
        if not self._client:
            raise RuntimeError("MQTT client not configured")
        self._client.connect(MQTT_HOST, MQTT_PORT)
        self._client.loop_start()
        logger.info("MQTT connected to %s:%d", MQTT_HOST, MQTT_PORT)

    def disconnect(self):
        if self._client and self._client.is_connected():
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTT disconnected")

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        # paho-mqtt v2 passes ReasonCode objects, not ints
        rc_value = rc.value if hasattr(rc, 'value') else rc
        if rc_value == 0:
            logger.info("MQTT connected, subscribing to topics")
            topic = f"{self._product_id}/{self._uid}/upload/pointdata"
            client.subscribe(topic)
            logger.info("Subscribed to %s", topic)
        else:
            logger.error("MQTT connection failed: %s", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if self._on_zone_update:
                self._on_zone_update(payload)
        except Exception:
            logger.exception("Error processing MQTT message")

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        rc_value = rc.value if hasattr(rc, 'value') else rc
        if rc_value != 0:
            logger.warning("MQTT unexpected disconnect: %s", rc)

    def send_zone_command(self, zone_mac: str, commands: list[ZoneCommand]) -> bool:
        """Send commands to a zone via MQTT."""
        if not self._client or not self._client.is_connected():
            raise RuntimeError("MQTT not connected")

        cmd_b64 = commands_to_base64(commands)

        msg = json.dumps({
            "common": {
                "serial": 7870,
                "productId": self._product_id,
                "uid": self._uid,
                "timestamp": str(int(time.time() * 1000)),
            },
            "data": {
                "mac": zone_mac,
                "pointData": cmd_b64,
            },
        })

        topic = f"{self._product_id}/{self._uid}/download/pointdata"
        result = self._client.publish(topic, msg, qos=0)
        try:
            result.wait_for_publish(timeout=5)
            return result.is_published()
        except Exception:
            logger.exception("Failed to publish MQTT command")
            return False

    def set_target_temperature(self, zone_mac: str, temperature: float) -> bool:
        return self.send_zone_command(zone_mac, [ZoneCommand("TARGET_TEMP", temperature)])

    def set_mode(self, zone_mac: str, mode: int) -> bool:
        return self.send_zone_command(zone_mac, [ZoneCommand("MODE", mode)])

    def activate_boost(
        self, zone_mac: str, hours: int = 1, temperature: Optional[float] = None
    ) -> bool:
        commands = [ZoneCommand("BOOST_HOURS", hours)]
        if temperature is not None:
            commands.append(ZoneCommand("BOOST_TEMP", temperature))
        commands.append(ZoneCommand("BOOST_TIME", int(time.time())))
        return self.send_zone_command(zone_mac, commands)

    def deactivate_boost(self, zone_mac: str) -> bool:
        return self.send_zone_command(zone_mac, [ZoneCommand("BOOST_HOURS", 0)])

    def set_advance(self, zone_mac: str, active: bool = True) -> bool:
        return self.send_zone_command(
            zone_mac, [ZoneCommand("ADVANCE_ACTIVE", 1 if active else 0)]
        )
