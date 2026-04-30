"""Tests for ScrutinyOptionsFlowHandler (options_flow.py).

Covers: form display, successful save, invalid scan interval.
Uses ha_stubs — no HA installation required.
"""

import asyncio
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)

import ha_stubs as stubs

stubs.install()

from ha_stubs import ConfigEntry, reset_registry

from custom_components.scrutiny.const import (
    CONF_ENABLE_ALL_ATTRS,
    CONF_ENABLE_CRITICAL_ATTRS,
    CONF_ENABLE_RAW_VALUES,
    CONF_SCAN_INTERVAL,
    CONF_SHOW_ARCHIVED,
    DEFAULT_ENABLE_ALL_ATTRS,
    DEFAULT_ENABLE_CRITICAL_ATTRS,
    DEFAULT_ENABLE_RAW_VALUES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_SHOW_ARCHIVED,
)
from custom_components.scrutiny.options_flow import ScrutinyOptionsFlowHandler

run = asyncio.run


def _make_handler(options=None):
    entry = ConfigEntry(
        entry_id="opts_entry",
        data={},
        options=options or {},
    )
    handler = ScrutinyOptionsFlowHandler()
    # OptionsFlow.config_entry is normally injected by HA; wire it directly here.
    handler.config_entry = entry
    return handler, entry


class TestOptionsFlow(unittest.TestCase):
    def setUp(self):
        reset_registry()

    def test_shows_form_when_no_input(self):
        handler, _ = _make_handler()
        result = run(handler.async_step_init(None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "init")

    def test_save_new_scan_interval(self):
        handler, entry = _make_handler(
            options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES}
        )
        result = run(handler.async_step_init({CONF_SCAN_INTERVAL: 15}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"][CONF_SCAN_INTERVAL], 15)
        # Booleans should default to False when not submitted
        self.assertFalse(result["data"][CONF_SHOW_ARCHIVED])
        self.assertFalse(result["data"][CONF_ENABLE_CRITICAL_ATTRS])
        self.assertFalse(result["data"][CONF_ENABLE_ALL_ATTRS])
        self.assertFalse(result["data"][CONF_ENABLE_RAW_VALUES])

    def test_save_all_options(self):
        handler, _ = _make_handler()
        user_input = {
            CONF_SCAN_INTERVAL: 30,
            CONF_SHOW_ARCHIVED: True,
            CONF_ENABLE_CRITICAL_ATTRS: True,
            CONF_ENABLE_ALL_ATTRS: False,
            CONF_ENABLE_RAW_VALUES: True,
        }
        result = run(handler.async_step_init(user_input))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"][CONF_SCAN_INTERVAL], 30)
        self.assertTrue(result["data"][CONF_SHOW_ARCHIVED])
        self.assertTrue(result["data"][CONF_ENABLE_CRITICAL_ATTRS])
        self.assertFalse(result["data"][CONF_ENABLE_ALL_ATTRS])
        self.assertTrue(result["data"][CONF_ENABLE_RAW_VALUES])

    def test_invalid_scan_interval_zero(self):
        handler, _ = _make_handler()
        result = run(handler.async_step_init({CONF_SCAN_INTERVAL: 0}))
        self.assertEqual(result["type"], "form")
        self.assertIn("scan_interval", result["errors"])

    def test_invalid_scan_interval_negative(self):
        handler, _ = _make_handler()
        result = run(handler.async_step_init({CONF_SCAN_INTERVAL: -5}))
        self.assertEqual(result["type"], "form")
        self.assertIn("scan_interval", result["errors"])

    def test_defaults_used_when_no_existing_options(self):
        """Options fallback to DEFAULT_* when none are stored yet."""
        handler, _ = _make_handler(options={})
        result = run(
            handler.async_step_init({CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES})
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(
            result["data"][CONF_SCAN_INTERVAL], DEFAULT_SCAN_INTERVAL_MINUTES
        )
        self.assertEqual(result["data"][CONF_SHOW_ARCHIVED], DEFAULT_SHOW_ARCHIVED)
        self.assertEqual(
            result["data"][CONF_ENABLE_CRITICAL_ATTRS], DEFAULT_ENABLE_CRITICAL_ATTRS
        )
        self.assertEqual(
            result["data"][CONF_ENABLE_ALL_ATTRS], DEFAULT_ENABLE_ALL_ATTRS
        )
        self.assertEqual(
            result["data"][CONF_ENABLE_RAW_VALUES], DEFAULT_ENABLE_RAW_VALUES
        )


if __name__ == "__main__":
    unittest.main()
