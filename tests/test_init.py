"""Tests for integration setup and teardown (__init__.py).

Covers: async_setup_entry success, first-refresh failure, and
async_unload_entry.  Uses ha_stubs — no HA installation required.
"""

import asyncio
import os
import sys
import unittest
import unittest.mock
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)

import ha_stubs as stubs

stubs.install()

from ha_stubs import ConfigEntry, HomeAssistant, UpdateFailed, reset_registry

from custom_components.scrutiny.const import (
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_VERIFY_SSL,
)

run = asyncio.run

MOCK_DATA = {
    CONF_URL: "http://test-scrutiny.local:8088",
    CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
}


class TestAsyncSetupEntry(unittest.TestCase):
    def setUp(self):
        reset_registry()
        self.hass = HomeAssistant()
        self.entry = ConfigEntry(entry_id="entry_test", data=MOCK_DATA, options={})

    def test_success(self):
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock(return_value=None)
        mock_coord.data = {"some_wwn": {}}

        with (
            patch(
                "custom_components.scrutiny.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch("custom_components.scrutiny.ScrutinyApiClient", autospec=True),
            patch(
                "custom_components.scrutiny.ScrutinyDataUpdateCoordinator",
                return_value=mock_coord,
            ),
            patch(
                "custom_components.scrutiny.dr.async_get",
                return_value=MagicMock(async_get_or_create=MagicMock()),
            ),
        ):
            from custom_components.scrutiny import async_setup_entry

            result = run(async_setup_entry(self.hass, self.entry))

        self.assertTrue(result)
        mock_coord.async_config_entry_first_refresh.assert_called_once()
        self.assertEqual(self.entry.runtime_data, mock_coord)

    def test_first_refresh_failure_raises(self):
        mock_coord = MagicMock()
        mock_coord.async_config_entry_first_refresh = AsyncMock(
            side_effect=UpdateFailed("simulated first refresh failure")
        )

        with (
            patch(
                "custom_components.scrutiny.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch("custom_components.scrutiny.ScrutinyApiClient", autospec=True),
            patch(
                "custom_components.scrutiny.ScrutinyDataUpdateCoordinator",
                return_value=mock_coord,
            ),
        ):
            from custom_components.scrutiny import async_setup_entry

            with self.assertRaises(UpdateFailed) as ctx:
                run(async_setup_entry(self.hass, self.entry))

        self.assertIn("first refresh failure", str(ctx.exception))


class TestAsyncUnloadEntry(unittest.TestCase):
    def setUp(self):
        reset_registry()
        self.hass = HomeAssistant()
        self.entry = ConfigEntry(entry_id="entry_unload", data=MOCK_DATA)

    def test_unload_success(self):
        self.hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        from custom_components.scrutiny import async_unload_entry

        result = run(async_unload_entry(self.hass, self.entry))
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
