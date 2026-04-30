"""Tests for the sensor platform (sensor.py).

Covers: async_setup_entry entity creation counts, ScrutinyMainDiskSensor
state calculation for all main sensor keys, ScrutinySmartAttributeSensor
availability, state updates, name fallback, and ScrutinySmartRawValueSensor.
Uses ha_stubs — no HA installation required.
"""

import asyncio
import copy
import os
import sys
import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)

import ha_stubs as stubs

stubs.install()

from ha_stubs import ConfigEntry, DeviceInfo, HomeAssistant, reset_registry

from custom_components.scrutiny.const import (
    ATTR_ARCHIVED,
    ATTR_ATTRIBUTE_ID,
    ATTR_CAPACITY,
    ATTR_DEVICE_NAME,
    ATTR_DISPLAY_NAME,
    ATTR_FIRMWARE,
    ATTR_MODEL_NAME,
    ATTR_POWER_CYCLE_COUNT,
    ATTR_POWER_ON_HOURS,
    ATTR_RAW_STRING,
    ATTR_RAW_VALUE,
    ATTR_SERIAL_NUMBER,
    ATTR_SMART_ATTRIBUTE_STATUS_CODE,
    ATTR_SMART_ATTRS,
    ATTR_SMART_OVERALL_STATUS,
    ATTR_SMART_STATUS_MAP,
    ATTR_SUMMARY_DEVICE_STATUS,
    ATTR_TEMPERATURE,
    ATTR_UPDATED_AT,
    ATTR_WHEN_FAILED,
    CONF_URL,
    DOMAIN,
    KEY_DETAILS_METADATA,
    KEY_DETAILS_SMART_LATEST,
    KEY_SUMMARY_DEVICE,
    KEY_SUMMARY_SMART,
    SCRUTINY_DEVICE_SUMMARY_STATUS_MAP,
    SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN,
)
from custom_components.scrutiny.coordinator import ScrutinyDataUpdateCoordinator
from custom_components.scrutiny.sensor import (
    MAIN_DISK_SENSOR_DESCRIPTIONS,
    ScrutinyMainDiskSensor,
    ScrutinySmartAttributeSensor,
    ScrutinySmartRawValueSensor,
    async_setup_entry,
)

run = asyncio.run

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

DISK_ID_1 = "a1b2c3d4-e5f6-7001-abcd-000000000001"
DISK_ID_2 = "a1b2c3d4-e5f6-7002-abcd-000000000002"
SERIAL1 = "SN_DISK1_ABC123"
SERIAL2 = "SN_DISK2_XYZ789"

COORDINATOR_DATA_ONE_DISK = {
    DISK_ID_1: {
        KEY_SUMMARY_DEVICE: {
            ATTR_DEVICE_NAME: "/dev/sda",
            ATTR_MODEL_NAME: "TestModelSDX",
            ATTR_FIRMWARE: "FW123",
            "manufacturer": "TestManu",
            ATTR_CAPACITY: 1000 * 1024**3,  # 1 TB
            ATTR_SUMMARY_DEVICE_STATUS: 0,
            ATTR_SERIAL_NUMBER: SERIAL1,
            ATTR_UPDATED_AT: "2025-08-06T07:00:13.499643907Z",
        },
        KEY_SUMMARY_SMART: {ATTR_TEMPERATURE: 25, ATTR_POWER_ON_HOURS: 100},
        KEY_DETAILS_SMART_LATEST: {
            ATTR_TEMPERATURE: 28,
            ATTR_POWER_ON_HOURS: 105,
            ATTR_POWER_CYCLE_COUNT: 10,
            ATTR_SMART_OVERALL_STATUS: 0,
            ATTR_SMART_ATTRS: {
                "5": {
                    ATTR_ATTRIBUTE_ID: 5,
                    "value": 100,
                    "raw_value": "0",
                    ATTR_SMART_ATTRIBUTE_STATUS_CODE: 0,
                },
                "194": {
                    ATTR_ATTRIBUTE_ID: 194,
                    "value": 72,
                    "raw_value": "28",
                    ATTR_SMART_ATTRIBUTE_STATUS_CODE: 0,
                },
            },
        },
        KEY_DETAILS_METADATA: {
            "5": {ATTR_DISPLAY_NAME: "Reallocated Sectors Count", "critical": True},
            "194": {ATTR_DISPLAY_NAME: "Temperature Celsius", "critical": False},
        },
    }
}


def _make_coordinator(data, last_update_success=True):
    coord = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    coord.data = data
    coord.last_update_success = last_update_success
    return coord


def _make_entry(options=None):
    return ConfigEntry(
        entry_id="test_entry_id_sensor",
        data={CONF_URL: "http://scrutiny.local:8080"},
        options=options or {},
    )


def _make_device_info(disk_id, data):
    summary = data.get(disk_id, {}).get(KEY_SUMMARY_DEVICE, {})
    serial = summary.get(ATTR_SERIAL_NUMBER)
    model = summary.get(ATTR_MODEL_NAME, "Disk")
    id_part = serial or disk_id[-6:]
    return DeviceInfo(
        identifiers={(DOMAIN, disk_id)},
        name=f"{model} ({id_part})",
        model=model,
        serial_number=serial,
        manufacturer=summary.get("manufacturer") or "Scrutiny",
        sw_version=summary.get(ATTR_FIRMWARE),
    )


# ---------------------------------------------------------------------------
# async_setup_entry
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry(unittest.TestCase):
    def setUp(self):
        reset_registry()

    def test_one_disk_default_options_creates_main_sensors_only(self):
        """Default options (no SMART attrs opted in): only main sensors are created."""
        coord = _make_coordinator(COORDINATOR_DATA_ONE_DISK)
        entry = _make_entry()
        entry.runtime_data = coord

        added = []
        run(
            async_setup_entry(
                HomeAssistant(), entry, lambda entities: added.extend(entities)
            )
        )

        self.assertEqual(len(added), len(MAIN_DISK_SENSOR_DESCRIPTIONS))
        self.assertTrue(all(isinstance(e, ScrutinyMainDiskSensor) for e in added))

    def test_smart_critical_attrs_opt_in(self):
        """Critical-attrs opt-in: attribute sensors for critical attributes only."""
        from custom_components.scrutiny.const import CONF_ENABLE_CRITICAL_ATTRS

        coord = _make_coordinator(COORDINATOR_DATA_ONE_DISK)
        entry = _make_entry(options={CONF_ENABLE_CRITICAL_ATTRS: True})
        entry.runtime_data = coord

        added = []
        run(
            async_setup_entry(
                HomeAssistant(), entry, lambda entities: added.extend(entities)
            )
        )

        smart_sensors = [
            e for e in added if isinstance(e, ScrutinySmartAttributeSensor)
        ]
        # Only attribute "5" is critical; "194" is not
        self.assertEqual(len(smart_sensors), 1)
        self.assertEqual(smart_sensors[0]._attribute_id_str, "5")

    def test_smart_all_attrs_opt_in(self):
        """All-attrs opt-in: attribute sensors created for every SMART attribute."""
        from custom_components.scrutiny.const import CONF_ENABLE_ALL_ATTRS

        coord = _make_coordinator(COORDINATOR_DATA_ONE_DISK)
        entry = _make_entry(options={CONF_ENABLE_ALL_ATTRS: True})
        entry.runtime_data = coord

        added = []
        run(
            async_setup_entry(
                HomeAssistant(), entry, lambda entities: added.extend(entities)
            )
        )

        smart_sensors = [
            e for e in added if isinstance(e, ScrutinySmartAttributeSensor)
        ]
        self.assertEqual(len(smart_sensors), 2)  # attrs "5" and "194"

    def test_raw_value_sensors_created_when_enabled(self):
        from custom_components.scrutiny.const import (
            CONF_ENABLE_ALL_ATTRS,
            CONF_ENABLE_RAW_VALUES,
        )

        coord = _make_coordinator(COORDINATOR_DATA_ONE_DISK)
        entry = _make_entry(
            options={CONF_ENABLE_ALL_ATTRS: True, CONF_ENABLE_RAW_VALUES: True}
        )
        entry.runtime_data = coord

        added = []
        run(
            async_setup_entry(
                HomeAssistant(), entry, lambda entities: added.extend(entities)
            )
        )

        raw_sensors = [e for e in added if isinstance(e, ScrutinySmartRawValueSensor)]
        self.assertEqual(len(raw_sensors), 2)

    def test_no_data_skips_setup(self):
        coord = _make_coordinator(None)
        entry = _make_entry()
        entry.runtime_data = coord

        added = []
        run(
            async_setup_entry(
                HomeAssistant(), entry, lambda entities: added.extend(entities)
            )
        )
        self.assertEqual(len(added), 0)

    def test_empty_data_dict_skips_setup(self):
        coord = _make_coordinator({})
        entry = _make_entry()
        entry.runtime_data = coord

        added = []
        run(
            async_setup_entry(
                HomeAssistant(), entry, lambda entities: added.extend(entities)
            )
        )
        self.assertEqual(len(added), 0)


# ---------------------------------------------------------------------------
# ScrutinyMainDiskSensor
# ---------------------------------------------------------------------------


class TestMainDiskSensor(unittest.TestCase):
    def _make_sensor(self, key, data=None, last_success=True):
        data = data or COORDINATOR_DATA_ONE_DISK
        coord = _make_coordinator(data, last_success)
        desc = next(d for d in MAIN_DISK_SENSOR_DESCRIPTIONS if d.key == key)
        return ScrutinyMainDiskSensor(
            coordinator=coord,
            entity_description=desc,
            disk_id=DISK_ID_1,
            device_info=_make_device_info(DISK_ID_1, data),
            serial_number=SERIAL1,
            is_archived=False,
        )

    def test_temperature_reads_from_details(self):
        sensor = self._make_sensor(ATTR_TEMPERATURE)
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 28)  # from KEY_DETAILS_SMART_LATEST

    def test_temperature_falls_back_to_summary(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        del data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_TEMPERATURE]
        sensor = self._make_sensor(ATTR_TEMPERATURE, data=data)
        self.assertEqual(sensor.native_value, 25)  # from KEY_SUMMARY_SMART

    def test_power_on_hours(self):
        sensor = self._make_sensor(ATTR_POWER_ON_HOURS)
        self.assertEqual(sensor.native_value, 105)

    def test_device_status_mapping(self):
        sensor = self._make_sensor(ATTR_SUMMARY_DEVICE_STATUS)
        self.assertEqual(sensor.native_value, SCRUTINY_DEVICE_SUMMARY_STATUS_MAP[0])

    def test_device_status_unknown_when_none(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        data[DISK_ID_1][KEY_SUMMARY_DEVICE][ATTR_SUMMARY_DEVICE_STATUS] = None
        sensor = self._make_sensor(ATTR_SUMMARY_DEVICE_STATUS, data=data)
        self.assertEqual(sensor.native_value, SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN)

    def test_capacity_converted_to_gigabytes(self):
        sensor = self._make_sensor(ATTR_CAPACITY)
        # 1000 * 1024^3 bytes → gigabytes (base-2)
        expected = round(
            COORDINATOR_DATA_ONE_DISK[DISK_ID_1][KEY_SUMMARY_DEVICE][ATTR_CAPACITY]
            / (1024**3),
            2,
        )
        self.assertAlmostEqual(sensor.native_value, expected, places=2)

    def test_power_cycle_count(self):
        sensor = self._make_sensor(ATTR_POWER_CYCLE_COUNT)
        self.assertEqual(sensor.native_value, 10)

    def test_smart_overall_status(self):
        sensor = self._make_sensor(ATTR_SMART_OVERALL_STATUS)
        self.assertEqual(sensor.native_value, ATTR_SMART_STATUS_MAP[0])

    def test_timestamp_parsed_correctly(self):
        sensor = self._make_sensor(ATTR_UPDATED_AT)
        expected = datetime(2025, 8, 6, 7, 0, 13, 499643, tzinfo=UTC)
        self.assertIsInstance(sensor.native_value, datetime)
        self.assertEqual(sensor.native_value, expected)

    def test_timestamp_missing_returns_none(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        del data[DISK_ID_1][KEY_SUMMARY_DEVICE][ATTR_UPDATED_AT]
        sensor = self._make_sensor(ATTR_UPDATED_AT, data=data)
        self.assertIsNone(sensor.native_value)

    def test_timestamp_malformed_returns_none(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        data[DISK_ID_1][KEY_SUMMARY_DEVICE][ATTR_UPDATED_AT] = "not-a-timestamp"
        sensor = self._make_sensor(ATTR_UPDATED_AT, data=data)
        self.assertIsNone(sensor.native_value)

    def test_unavailable_when_coordinator_failed(self):
        sensor = self._make_sensor(ATTR_TEMPERATURE, last_success=False)
        self.assertFalse(sensor.available)
        self.assertIsNone(sensor.native_value)

    def test_unavailable_when_disk_id_missing_from_data(self):
        coord = _make_coordinator({})
        desc = next(
            d for d in MAIN_DISK_SENSOR_DESCRIPTIONS if d.key == ATTR_TEMPERATURE
        )
        sensor = ScrutinyMainDiskSensor(
            coordinator=coord,
            entity_description=desc,
            disk_id=DISK_ID_1,
            device_info=DeviceInfo(identifiers={(DOMAIN, DISK_ID_1)}, name="x"),
        )
        self.assertFalse(sensor.available)

    def test_handle_coordinator_update_writes_state(self):
        coord = _make_coordinator(COORDINATOR_DATA_ONE_DISK)
        desc = next(
            d for d in MAIN_DISK_SENSOR_DESCRIPTIONS if d.key == ATTR_TEMPERATURE
        )
        sensor = ScrutinyMainDiskSensor(
            coordinator=coord,
            entity_description=desc,
            disk_id=DISK_ID_1,
            device_info=_make_device_info(DISK_ID_1, COORDINATOR_DATA_ONE_DISK),
        )
        written = []
        sensor.async_write_ha_state = lambda: written.append(1)

        updated = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        updated[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_TEMPERATURE] = 45
        coord.data = updated
        sensor._handle_coordinator_update()

        self.assertEqual(sensor.native_value, 45)
        self.assertEqual(len(written), 1)

    def test_unique_id_format(self):
        sensor = self._make_sensor(ATTR_TEMPERATURE)
        self.assertEqual(sensor.unique_id, f"{DOMAIN}_{DISK_ID_1}_{ATTR_TEMPERATURE}")

    def test_extra_state_attributes_include_serial(self):
        sensor = self._make_sensor(ATTR_TEMPERATURE)
        self.assertEqual(sensor.extra_state_attributes.get(ATTR_SERIAL_NUMBER), SERIAL1)

    def test_archived_sensor_extra_attribute(self):
        coord = _make_coordinator(COORDINATOR_DATA_ONE_DISK)
        desc = next(
            d for d in MAIN_DISK_SENSOR_DESCRIPTIONS if d.key == ATTR_TEMPERATURE
        )
        sensor = ScrutinyMainDiskSensor(
            coordinator=coord,
            entity_description=desc,
            disk_id=DISK_ID_1,
            device_info=_make_device_info(DISK_ID_1, COORDINATOR_DATA_ONE_DISK),
            is_archived=True,
        )
        self.assertTrue(sensor.extra_state_attributes.get(ATTR_ARCHIVED))


# ---------------------------------------------------------------------------
# ScrutinySmartAttributeSensor
# ---------------------------------------------------------------------------


class TestSmartAttributeSensor(unittest.TestCase):
    def _make_sensor(self, attr_id="5", data=None, last_success=True):
        data = data or copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        coord = _make_coordinator(data, last_success)
        device_info = _make_device_info(DISK_ID_1, data)
        meta = data[DISK_ID_1][KEY_DETAILS_METADATA].get(attr_id, {})
        return ScrutinySmartAttributeSensor(
            coordinator=coord,
            disk_id=DISK_ID_1,
            device_info=device_info,
            attribute_id_str=attr_id,
            attribute_metadata=meta,
            serial_number=SERIAL1,
        )

    def test_initial_state_passed(self):
        sensor = self._make_sensor("5")
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, ATTR_SMART_STATUS_MAP[0])  # "Passed"

    def test_unique_id_format(self):
        from ha_stubs import slugify

        sensor = self._make_sensor("5")
        display = "Reallocated Sectors Count"
        self.assertEqual(
            sensor.unique_id,
            f"{DOMAIN}_{DISK_ID_1}_smart_{slugify('5')}_{slugify(display)}",
        )

    def test_name_from_metadata(self):
        sensor = self._make_sensor("5")
        self.assertEqual(sensor.entity_description.name, "Reallocated Sectors Count")

    def test_name_fallback_numeric_id(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["99"] = {
            ATTR_ATTRIBUTE_ID: 99,
            "value": 50,
            ATTR_SMART_ATTRIBUTE_STATUS_CODE: 0,
        }
        data[DISK_ID_1][KEY_DETAILS_METADATA]["99"] = {}
        sensor = self._make_sensor("99", data=data)
        self.assertEqual(sensor.entity_description.name, "Attribute 99")

    def test_name_fallback_string_id(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["critical_warning"] = {
            ATTR_ATTRIBUTE_ID: "critical_warning",
            "value": 0,
            ATTR_SMART_ATTRIBUTE_STATUS_CODE: 0,
        }
        data[DISK_ID_1][KEY_DETAILS_METADATA]["critical_warning"] = {}
        sensor = self._make_sensor("critical_warning", data=data)
        self.assertEqual(sensor.entity_description.name, "Critical Warning")

    def test_unavailable_when_coordinator_failed(self):
        sensor = self._make_sensor("5", last_success=False)
        self.assertFalse(sensor.available)

    def test_unavailable_when_attribute_missing(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        del data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["5"]
        sensor = self._make_sensor("5", data=data)
        self.assertFalse(sensor.available)
        self.assertIsNone(sensor.native_value)

    def test_handle_coordinator_update_state_change(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        coord = _make_coordinator(data)
        meta = data[DISK_ID_1][KEY_DETAILS_METADATA].get("194", {})
        sensor = ScrutinySmartAttributeSensor(
            coordinator=coord,
            disk_id=DISK_ID_1,
            device_info=_make_device_info(DISK_ID_1, data),
            attribute_id_str="194",
            attribute_metadata=meta,
        )
        written = []
        sensor.async_write_ha_state = lambda: written.append(1)

        updated = copy.deepcopy(data)
        updated[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["194"][
            ATTR_SMART_ATTRIBUTE_STATUS_CODE
        ] = 2  # Warning
        coord.data = updated
        sensor._handle_coordinator_update()

        self.assertEqual(sensor.native_value, ATTR_SMART_STATUS_MAP[2])
        self.assertEqual(len(written), 1)

    def test_handle_coordinator_update_no_write_when_remains_unavailable(self):
        """Sensor stays unavailable: async_write_ha_state must not be called."""
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        del data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["5"]
        coord = _make_coordinator(data)
        meta = {}
        sensor = ScrutinySmartAttributeSensor(
            coordinator=coord,
            disk_id=DISK_ID_1,
            device_info=_make_device_info(DISK_ID_1, data),
            attribute_id_str="5",
            attribute_metadata=meta,
        )
        # Sensor starts unavailable
        self.assertIsNone(sensor.native_value)
        written = []
        sensor.async_write_ha_state = lambda: written.append(1)

        sensor._handle_coordinator_update()
        self.assertEqual(len(written), 0)

    def test_extra_attributes_include_raw_value(self):
        sensor = self._make_sensor("5")
        attrs = sensor.extra_state_attributes
        self.assertIn(ATTR_RAW_VALUE, attrs)
        self.assertEqual(attrs[ATTR_RAW_VALUE], "0")

    def test_when_failed_dash_excluded(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["5"][
            ATTR_WHEN_FAILED
        ] = "-"
        sensor = self._make_sensor("5", data=data)
        self.assertNotIn(ATTR_WHEN_FAILED, sensor.extra_state_attributes)

    def test_when_failed_real_value_included(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["5"][
            ATTR_WHEN_FAILED
        ] = "FAILING_NOW"
        sensor = self._make_sensor("5", data=data)
        self.assertEqual(
            sensor.extra_state_attributes.get(ATTR_WHEN_FAILED), "FAILING_NOW"
        )


# ---------------------------------------------------------------------------
# ScrutinySmartRawValueSensor
# ---------------------------------------------------------------------------


class TestSmartRawValueSensor(unittest.TestCase):
    def _make_sensor(self, attr_id="5", data=None, last_success=True):
        data = data or copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        coord = _make_coordinator(data, last_success)
        meta = data[DISK_ID_1][KEY_DETAILS_METADATA].get(attr_id, {})
        return ScrutinySmartRawValueSensor(
            coordinator=coord,
            disk_id=DISK_ID_1,
            device_info=_make_device_info(DISK_ID_1, data),
            attribute_id_str=attr_id,
            attribute_metadata=meta,
            serial_number=SERIAL1,
        )

    def test_native_value_is_integer(self):
        sensor = self._make_sensor("5")
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.native_value, 0)  # raw_value "0"

    def test_native_value_non_zero(self):
        sensor = self._make_sensor("194")
        self.assertEqual(sensor.native_value, 28)  # raw_value "28"

    def test_unavailable_when_coordinator_failed(self):
        sensor = self._make_sensor("5", last_success=False)
        self.assertFalse(sensor.available)
        self.assertIsNone(sensor.native_value)

    def test_unique_id_format(self):
        from ha_stubs import slugify

        sensor = self._make_sensor("5")
        self.assertEqual(
            sensor.unique_id,
            f"{DOMAIN}_{DISK_ID_1}_smart_raw_"
            f"{slugify('5')}_{slugify('Reallocated Sectors Count')}",
        )

    def test_name_includes_raw_suffix(self):
        sensor = self._make_sensor("5")
        self.assertIn("Raw", sensor.entity_description.name)

    def test_extra_attributes_include_raw_string_when_present(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["5"][ATTR_RAW_STRING] = (
            "0 sectors"
        )
        sensor = self._make_sensor("5", data=data)
        self.assertIn(ATTR_RAW_STRING, sensor.extra_state_attributes)
        self.assertEqual(sensor.extra_state_attributes[ATTR_RAW_STRING], "0 sectors")

    def test_handle_coordinator_update_no_write_when_remains_unavailable(self):
        data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
        del data[DISK_ID_1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]["5"]
        coord = _make_coordinator(data)
        meta = {}
        sensor = ScrutinySmartRawValueSensor(
            coordinator=coord,
            disk_id=DISK_ID_1,
            device_info=_make_device_info(DISK_ID_1, data),
            attribute_id_str="5",
            attribute_metadata=meta,
        )
        self.assertIsNone(sensor.native_value)
        written = []
        sensor.async_write_ha_state = lambda: written.append(1)
        sensor._handle_coordinator_update()
        self.assertEqual(len(written), 0)


if __name__ == "__main__":
    unittest.main()
