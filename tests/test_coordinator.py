"""Tests for ScrutinyDataUpdateCoordinator (coordinator.py).

Covers: successful update cycle, connection errors, partial detail failure,
_process_detail_results edge cases, archived disk filtering, and stale
device cleanup.  Uses ha_stubs — no HA installation required.
"""

import asyncio
import os
import sys
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)

import ha_stubs as stubs

stubs.install()

from ha_stubs import (
    ConfigEntry,
    DeviceRegistry,
    HomeAssistant,
    UpdateFailed,
    reset_registry,
)

from custom_components.scrutiny.api import (
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
)
from custom_components.scrutiny.const import (
    ATTR_DEVICE,
    ATTR_METADATA,
    ATTR_SMART,
    ATTR_SMART_RESULTS,
    CONF_SHOW_ARCHIVED,
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
    KEY_DETAILS_METADATA,
    KEY_DETAILS_SMART_LATEST,
    LOGGER,
)
from custom_components.scrutiny.coordinator import ScrutinyDataUpdateCoordinator

run = asyncio.run

TB = 1024**4

MOCK_SUMMARY = {
    "uuid-disk-aaa1": {
        ATTR_DEVICE: {
            "device_name": "/dev/sda",
            "model_name": "DiskA",
            "archived": False,
        },
        ATTR_SMART: {"temp": 30, "power_on_hours": 1000},
    },
    "uuid-disk-bbb2": {
        ATTR_DEVICE: {
            "device_name": "/dev/sdb",
            "model_name": "DiskB",
            "archived": False,
        },
        ATTR_SMART: {"temp": 35, "power_on_hours": 2000},
    },
}

MOCK_DETAILS_DISK1 = {
    "success": True,
    "data": {
        ATTR_DEVICE: {"device_name": "/dev/sda", "capacity": TB},
        ATTR_SMART_RESULTS: [
            {"attrs": {"5": {"attribute_id": 5, "value": 100}}, "Status": 0, "temp": 31}
        ],
    },
    ATTR_METADATA: {"5": {"display_name": "Reallocated Sectors Count"}},
}

MOCK_DETAILS_DISK2 = {
    "success": True,
    "data": {
        ATTR_DEVICE: {"device_name": "/dev/sdb", "capacity": 2 * TB},
        ATTR_SMART_RESULTS: [
            {
                "attrs": {"194": {"attribute_id": 194, "value": 36}},
                "Status": 0,
                "temp": 36,
            }
        ],
    },
    ATTR_METADATA: {"194": {"display_name": "Temperature Celsius"}},
}


def _make_coordinator(hass, api_client, entry=None):
    return ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        config_entry=entry,
        name="scrutiny-test",
        api_client=api_client,
        update_interval=timedelta(seconds=30),
    )


class TestCoordinatorSuccessPath(unittest.TestCase):
    def setUp(self):
        reset_registry()
        self.hass = HomeAssistant()

    def test_full_update_success(self):
        async def _details(wwn):
            return MOCK_DETAILS_DISK1 if wwn == "uuid-disk-aaa1" else MOCK_DETAILS_DISK2

        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(return_value=MOCK_SUMMARY)
        client.async_get_device_details = AsyncMock(side_effect=_details)

        coord = _make_coordinator(self.hass, client)
        run(coord.async_refresh())

        self.assertTrue(coord.last_update_success)
        self.assertIn("uuid-disk-aaa1", coord.data)
        self.assertIn("uuid-disk-bbb2", coord.data)
        self.assertEqual(coord.data["uuid-disk-aaa1"][KEY_DETAILS_SMART_LATEST]["temp"], 31)
        self.assertEqual(
            coord.data["uuid-disk-aaa1"][KEY_DETAILS_METADATA],
            MOCK_DETAILS_DISK1[ATTR_METADATA],
        )

    def test_empty_summary(self):
        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(return_value={})
        client.async_get_device_details = AsyncMock()

        coord = _make_coordinator(self.hass, client)
        run(coord.async_refresh())

        self.assertTrue(coord.last_update_success)
        self.assertEqual(coord.data, {})
        client.async_get_device_details.assert_not_called()

    def test_partial_detail_failure(self):
        """Detail fetch failure for one disk is graceful; other disks still update."""

        async def _details(wwn):
            if wwn == "uuid-disk-bbb2":
                raise ScrutinyApiResponseError("simulated detail error for wwn2")
            return MOCK_DETAILS_DISK1

        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(return_value=MOCK_SUMMARY)
        client.async_get_device_details = AsyncMock(side_effect=_details)

        coord = _make_coordinator(self.hass, client)
        run(coord.async_refresh())

        self.assertTrue(coord.last_update_success)
        # uuid-disk-aaa1 has real detail data
        self.assertEqual(coord.data["uuid-disk-aaa1"][KEY_DETAILS_SMART_LATEST]["temp"], 31)
        # uuid-disk-bbb2 fell back to empty dicts
        self.assertEqual(coord.data["uuid-disk-bbb2"][KEY_DETAILS_SMART_LATEST], {})
        self.assertEqual(coord.data["uuid-disk-bbb2"][KEY_DETAILS_METADATA], {})


class TestCoordinatorErrorPaths(unittest.TestCase):
    def setUp(self):
        reset_registry()
        self.hass = HomeAssistant()

    def test_connection_error_on_summary(self):
        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(
            side_effect=ScrutinyApiConnectionError("simulated connection error")
        )

        coord = _make_coordinator(self.hass, client)
        run(coord.async_refresh())

        self.assertFalse(coord.last_update_success)
        self.assertIsInstance(coord.last_exception, UpdateFailed)
        self.assertIn("Connection error", str(coord.last_exception))
        self.assertIsNone(coord.data)

    def test_invalid_summary_type(self):
        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(return_value="not a dict")

        coord = _make_coordinator(self.hass, client)
        run(coord.async_refresh())

        self.assertFalse(coord.last_update_success)
        self.assertIsInstance(coord.last_exception, UpdateFailed)


class TestProcessDetailResults(unittest.TestCase):
    def setUp(self):
        reset_registry()
        self.hass = HomeAssistant()
        client = MagicMock(spec=ScrutinyApiClient)
        self.coord = _make_coordinator(self.hass, client)

    def _call(self, disk_id, response):
        target = {}
        self.coord._process_detail_results(disk_id, response, target)
        return target

    def test_valid_input(self):
        result = self._call("uuid-disk-aaa1", MOCK_DETAILS_DISK1)
        self.assertEqual(
            result[KEY_DETAILS_SMART_LATEST],
            MOCK_DETAILS_DISK1["data"][ATTR_SMART_RESULTS][0],
        )
        self.assertEqual(result[KEY_DETAILS_METADATA], MOCK_DETAILS_DISK1[ATTR_METADATA])

    def test_exception_input(self):
        result = self._call("uuid-disk-aaa1", ValueError("simulated"))
        self.assertEqual(result[KEY_DETAILS_SMART_LATEST], {})
        self.assertEqual(result[KEY_DETAILS_METADATA], {})

    def test_missing_data_key(self):
        faulty = {"success": True, ATTR_METADATA: {"1": {"display_name": "Test"}}}
        result = self._call("uuid-disk-aaa1", faulty)
        self.assertEqual(result[KEY_DETAILS_SMART_LATEST], {})
        self.assertEqual(result[KEY_DETAILS_METADATA], faulty[ATTR_METADATA])

    def test_missing_smart_results(self):
        faulty = {
            "success": True,
            "data": {ATTR_DEVICE: {"model_name": "Disk"}},
            ATTR_METADATA: {"1": {"display_name": "Test"}},
        }
        result = self._call("uuid-disk-aaa1", faulty)
        self.assertEqual(result[KEY_DETAILS_SMART_LATEST], {})

    def test_empty_smart_results_list(self):
        faulty = {
            "success": True,
            "data": {ATTR_DEVICE: {"model_name": "Disk"}, ATTR_SMART_RESULTS: []},
            ATTR_METADATA: {"1": {"display_name": "Test"}},
        }
        result = self._call("uuid-disk-aaa1", faulty)
        self.assertEqual(result[KEY_DETAILS_SMART_LATEST], {})

    def test_missing_metadata_key(self):
        faulty = {
            "success": True,
            "data": {
                ATTR_DEVICE: {"model_name": "Disk"},
                ATTR_SMART_RESULTS: [{"attrs": {}, "Status": 0}],
            },
        }
        result = self._call("uuid-disk-aaa1", faulty)
        self.assertEqual(
            result[KEY_DETAILS_SMART_LATEST], faulty["data"][ATTR_SMART_RESULTS][0]
        )
        self.assertEqual(result[KEY_DETAILS_METADATA], {})


class TestArchivedFiltering(unittest.TestCase):
    def setUp(self):
        reset_registry()
        self.hass = HomeAssistant()

    SUMMARY_WITH_ARCHIVED = {
        "uuid-disk-aaa1": {
            ATTR_DEVICE: {
                "device_name": "/dev/sda",
                "model_name": "Active",
                "archived": False,
            },
            ATTR_SMART: {"temp": 30},
        },
        "uuid-disk-arc0": {
            ATTR_DEVICE: {
                "device_name": "/dev/sdb",
                "model_name": "OldDisk",
                "archived": True,
            },
            ATTR_SMART: {"temp": 25},
        },
    }

    EMPTY_DETAILS = {"data": {ATTR_SMART_RESULTS: []}, ATTR_METADATA: {}}

    def _make_entry(self, show_archived):
        return ConfigEntry(
            data={CONF_URL: "http://localhost:8080", CONF_VERIFY_SSL: True},
            options={CONF_SHOW_ARCHIVED: show_archived},
        )

    def test_archived_excluded_when_disabled(self):
        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(return_value=self.SUMMARY_WITH_ARCHIVED)
        client.async_get_device_details = AsyncMock(return_value=self.EMPTY_DETAILS)

        coord = _make_coordinator(self.hass, client, entry=self._make_entry(False))
        data = run(coord._async_update_data())

        self.assertIn("uuid-disk-aaa1", data)
        self.assertNotIn("uuid-disk-arc0", data)

    def test_archived_included_when_enabled(self):
        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(return_value=self.SUMMARY_WITH_ARCHIVED)
        client.async_get_device_details = AsyncMock(return_value=self.EMPTY_DETAILS)

        coord = _make_coordinator(self.hass, client, entry=self._make_entry(True))
        data = run(coord._async_update_data())

        self.assertIn("uuid-disk-aaa1", data)
        self.assertIn("uuid-disk-arc0", data)


class TestStaleDeviceCleanup(unittest.TestCase):
    def setUp(self):
        reset_registry()
        self.hass = HomeAssistant()

    def test_stale_disk_device_removed(self):
        entry = ConfigEntry(
            entry_id="entry123",
            data={CONF_URL: "http://localhost:8080", CONF_VERIFY_SSL: True},
            options={CONF_SHOW_ARCHIVED: False},
        )

        # Seed the registry: one live disk (wwn1) and one stale disk (wwn_gone)
        from ha_stubs import async_get as dr_async_get

        registry: DeviceRegistry = dr_async_get(self.hass)
        # Hub device (entry_id identifier — should not be cleaned up)
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name="Hub",
        )
        # Live disk
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, "uuid-disk-aaa1")},
            name="DiskA",
        )
        # Stale disk no longer returned by Scrutiny
        stale = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, "uuid-disk-gone")},
            name="GoneDisk",
        )

        # Coordinator update returns only wwn1
        summary = {
            "uuid-disk-aaa1": {
                ATTR_DEVICE: {
                    "device_name": "/dev/sda",
                    "model_name": "DiskA",
                    "archived": False,
                },
                ATTR_SMART: {"temp": 30},
            },
        }
        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(return_value=summary)
        client.async_get_device_details = AsyncMock(
            return_value={"data": {ATTR_SMART_RESULTS: []}, ATTR_METADATA: {}}
        )

        coord = _make_coordinator(self.hass, client, entry=entry)
        run(coord.async_refresh())

        # Stale disk should have been removed
        self.assertIn(stale.id, registry._removed)

    def test_no_cleanup_on_empty_api_response(self):
        """If the API returns zero disks, devices must NOT be cleaned up."""
        entry = ConfigEntry(
            entry_id="entry456",
            data={CONF_URL: "http://localhost:8080", CONF_VERIFY_SSL: True},
            options={CONF_SHOW_ARCHIVED: False},
        )
        from ha_stubs import async_get as dr_async_get

        registry: DeviceRegistry = dr_async_get(self.hass)
        existing = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, "uuid-disk-aaa1")},
            name="DiskA",
        )

        client = MagicMock(spec=ScrutinyApiClient)
        client.async_get_summary = AsyncMock(return_value={})
        client.async_get_device_details = AsyncMock()

        coord = _make_coordinator(self.hass, client, entry=entry)
        run(coord.async_refresh())

        # Device must still be there — empty response must not trigger cleanup
        self.assertNotIn(existing.id, registry._removed)


if __name__ == "__main__":
    unittest.main()
