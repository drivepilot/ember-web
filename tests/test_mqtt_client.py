"""Tests for the MQTT client - command encoding and message formatting."""

import sys
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from mqtt_client import ZoneCommand, commands_to_base64, EmberMQTTClient


class TestZoneCommand:
    def test_target_temp_to_ints(self):
        cmd = ZoneCommand("TARGET_TEMP", 21.5)
        ints = cmd.to_ints()
        # header: [0, index=6, type_id=4]
        assert ints[0] == 0
        assert ints[1] == 6   # TARGET_TEMP index
        assert ints[2] == 4   # TEMP_RW type id
        # value: 21.5 * 10 = 215, big-endian 2 bytes
        assert ints[3] == 0
        assert ints[4] == 215

    def test_mode_to_ints(self):
        cmd = ZoneCommand("MODE", 2)  # ON
        ints = cmd.to_ints()
        assert ints == [0, 7, 1, 2]  # [header, index=7, type=SMALL_INT(1), value=2]

    def test_boost_hours_to_ints(self):
        cmd = ZoneCommand("BOOST_HOURS", 1)
        ints = cmd.to_ints()
        assert ints == [0, 8, 1, 1]

    def test_boost_temp_to_ints(self):
        cmd = ZoneCommand("BOOST_TEMP", 22.0)
        ints = cmd.to_ints()
        assert ints[0] == 0
        assert ints[1] == 14   # BOOST_TEMP index
        assert ints[2] == 4    # TEMP_RW type
        # 22.0 * 10 = 220
        assert ints[3] == 0
        assert ints[4] == 220

    def test_boost_time_to_ints(self):
        cmd = ZoneCommand("BOOST_TIME", 1700000000)
        ints = cmd.to_ints()
        assert ints[0] == 0
        assert ints[1] == 9   # BOOST_TIME index
        assert ints[2] == 5   # TIMESTAMP type
        # 1700000000 as 4 big-endian bytes
        expected = list(int.to_bytes(1700000000, 4, "big"))
        assert ints[3:] == expected

    def test_advance_active_to_ints(self):
        cmd = ZoneCommand("ADVANCE_ACTIVE", 1)
        ints = cmd.to_ints()
        assert ints == [0, 4, 1, 1]

    def test_advance_inactive_to_ints(self):
        cmd = ZoneCommand("ADVANCE_ACTIVE", 0)
        ints = cmd.to_ints()
        assert ints == [0, 4, 1, 0]

    def test_readonly_raises(self):
        with pytest.raises(ValueError, match="read-only"):
            ZoneCommand("CURRENT_TEMP", 20.0)

    def test_invalid_command_raises(self):
        with pytest.raises(ValueError):
            ZoneCommand("NONEXISTENT", 0)

    def test_temp_encoding_fractional(self):
        """Test that fractional temperatures encode correctly."""
        cmd = ZoneCommand("TARGET_TEMP", 19.5)
        ints = cmd.to_ints()
        # 19.5 * 10 = 195
        value = int.from_bytes(bytes(ints[3:]), "big")
        assert value == 195

    def test_temp_encoding_whole(self):
        cmd = ZoneCommand("TARGET_TEMP", 20.0)
        ints = cmd.to_ints()
        value = int.from_bytes(bytes(ints[3:]), "big")
        assert value == 200


class TestCommandsToBase64:
    def test_single_command(self):
        cmds = [ZoneCommand("MODE", 3)]
        b64 = commands_to_base64(cmds)
        # Decode and verify
        decoded = list(base64.b64decode(b64))
        assert decoded == [0, 7, 1, 3]

    def test_multiple_commands(self):
        cmds = [
            ZoneCommand("BOOST_HOURS", 1),
            ZoneCommand("BOOST_TEMP", 22.0),
        ]
        b64 = commands_to_base64(cmds)
        decoded = list(base64.b64decode(b64))
        # First command: [0, 8, 1, 1]
        # Second command: [0, 14, 4, 0, 220]
        assert decoded[:4] == [0, 8, 1, 1]
        assert decoded[4] == 0
        assert decoded[5] == 14
        assert decoded[6] == 4

    def test_roundtrip(self):
        """Encode and decode should preserve the data."""
        cmds = [ZoneCommand("TARGET_TEMP", 21.0)]
        b64 = commands_to_base64(cmds)
        decoded = list(base64.b64decode(b64))
        assert decoded[0] == 0
        assert decoded[1] == 6
        value = int.from_bytes(bytes(decoded[3:]), "big")
        assert value == 210


class TestEmberMQTTClient:
    def test_not_configured_raises(self):
        client = EmberMQTTClient()
        with pytest.raises(RuntimeError, match="not configured"):
            client.connect()

    def test_is_connected_default(self):
        client = EmberMQTTClient()
        assert client.is_connected is False

    def test_disconnect_when_not_connected(self):
        client = EmberMQTTClient()
        # Should not raise
        client.disconnect()

    @patch("mqtt_client.mqtt.Client")
    def test_configure_sets_credentials(self, mock_mqtt_class):
        mock_instance = MagicMock()
        mock_mqtt_class.return_value = mock_instance

        client = EmberMQTTClient()
        client.configure(
            user_id="user-1",
            token="token-abc",
            product_id="PROD-1",
            uid="UID-1",
        )

        assert client._product_id == "PROD-1"
        assert client._uid == "UID-1"
        mock_instance.tls_set.assert_called_once()
        mock_instance.username_pw_set.assert_called_once_with("app/token-abc", "token-abc")

    @patch("mqtt_client.mqtt.Client")
    def test_send_zone_command_not_connected(self, mock_mqtt_class):
        mock_instance = MagicMock()
        mock_instance.is_connected.return_value = False
        mock_mqtt_class.return_value = mock_instance

        client = EmberMQTTClient()
        client.configure(
            user_id="user-1",
            token="token-abc",
            product_id="PROD-1",
            uid="UID-1",
        )

        with pytest.raises(RuntimeError, match="not connected"):
            client.send_zone_command("AA:BB:CC", [ZoneCommand("MODE", 0)])

    @patch("mqtt_client.mqtt.Client")
    def test_send_zone_command_publishes(self, mock_mqtt_class):
        mock_instance = MagicMock()
        mock_instance.is_connected.return_value = True
        mock_publish_result = MagicMock()
        mock_publish_result.is_published.return_value = True
        mock_instance.publish.return_value = mock_publish_result
        mock_mqtt_class.return_value = mock_instance

        client = EmberMQTTClient()
        client.configure(
            user_id="user-1",
            token="token-abc",
            product_id="PROD-1",
            uid="UID-1",
        )
        client._client = mock_instance

        result = client.send_zone_command("AA:BB:CC", [ZoneCommand("MODE", 2)])
        assert result is True
        mock_instance.publish.assert_called_once()

        # Verify the topic
        call_args = mock_instance.publish.call_args
        assert call_args[0][0] == "PROD-1/UID-1/download/pointdata"
