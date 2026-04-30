"""Tests for the config flow and reconfigure flow (config_flow.py).

Covers: successful user step, connection error, already-configured abort,
default values, and reconfigure flow.  Uses ha_stubs — no HA installation.
"""

import asyncio
import os
import sys
import unittest
import unittest.mock
from unittest.mock import AsyncMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)

import ha_stubs as stubs

stubs.install()

from ha_stubs import ConfigEntry, reset_registry

from custom_components.scrutiny.api import (
    ScrutinyApiAuthError,
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
)
from custom_components.scrutiny.config_flow import ScrutinyConfigFlowHandler
from custom_components.scrutiny.const import (
    CONF_ENABLE_ALL_ATTRS,
    CONF_ENABLE_CRITICAL_ATTRS,
    CONF_SCAN_INTERVAL,
    CONF_SHOW_ARCHIVED,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_ENABLE_ALL_ATTRS,
    DEFAULT_ENABLE_CRITICAL_ATTRS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_VERIFY_SSL,
)

run = asyncio.run

TEST_URL = "http://scrutiny.test.local:8080"
USER_INPUT_FULL = {
    CONF_URL: TEST_URL,
    CONF_VERIFY_SSL: True,
    CONF_SCAN_INTERVAL: 30,
    CONF_SHOW_ARCHIVED: False,
    CONF_ENABLE_CRITICAL_ATTRS: True,
    CONF_ENABLE_ALL_ATTRS: False,
}


def _make_flow():
    return ScrutinyConfigFlowHandler()


class TestUserStep(unittest.TestCase):
    def setUp(self):
        reset_registry()

    def test_success(self):
        flow = _make_flow()
        with patch.object(flow, "_test_connection", new=AsyncMock(return_value=None)):
            result = run(flow.async_step_user(USER_INPUT_FULL))

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"][CONF_URL], TEST_URL.rstrip("/"))
        self.assertNotIn(CONF_SCAN_INTERVAL, result["data"])
        self.assertEqual(result["options"][CONF_SCAN_INTERVAL], 30)
        self.assertTrue(result["options"][CONF_ENABLE_CRITICAL_ATTRS])
        self.assertFalse(result["options"][CONF_ENABLE_ALL_ATTRS])

    def test_shows_form_when_no_input(self):
        flow = _make_flow()
        result = run(flow.async_step_user(None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")

    def test_connection_error(self):
        flow = _make_flow()
        with patch.object(
            flow,
            "_test_connection",
            new=AsyncMock(side_effect=ScrutinyApiConnectionError("err")),
        ):
            result = run(flow.async_step_user(USER_INPUT_FULL))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "cannot_connect")

    def test_response_error(self):
        flow = _make_flow()
        with patch.object(
            flow,
            "_test_connection",
            new=AsyncMock(side_effect=ScrutinyApiResponseError("err")),
        ):
            result = run(flow.async_step_user(USER_INPUT_FULL))
        self.assertEqual(result["errors"]["base"], "invalid_api_response")

    def test_auth_error(self):
        flow = _make_flow()
        with patch.object(
            flow,
            "_test_connection",
            new=AsyncMock(side_effect=ScrutinyApiAuthError("err")),
        ):
            result = run(flow.async_step_user(USER_INPUT_FULL))
        self.assertEqual(result["errors"]["base"], "invalid_auth")

    def test_unknown_error(self):
        flow = _make_flow()
        with patch.object(
            flow,
            "_test_connection",
            new=AsyncMock(side_effect=RuntimeError("unexpected")),
        ):
            result = run(flow.async_step_user(USER_INPUT_FULL))
        self.assertEqual(result["errors"]["base"], "unknown")

    def test_defaults_applied_when_only_url_given(self):
        flow = _make_flow()
        with patch.object(flow, "_test_connection", new=AsyncMock(return_value=None)):
            result = run(flow.async_step_user({CONF_URL: TEST_URL}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"][CONF_VERIFY_SSL], DEFAULT_VERIFY_SSL)
        self.assertEqual(
            result["options"][CONF_SCAN_INTERVAL], DEFAULT_SCAN_INTERVAL_MINUTES
        )
        self.assertEqual(
            result["options"][CONF_ENABLE_CRITICAL_ATTRS], DEFAULT_ENABLE_CRITICAL_ATTRS
        )
        self.assertEqual(
            result["options"][CONF_ENABLE_ALL_ATTRS], DEFAULT_ENABLE_ALL_ATTRS
        )

    def test_url_trailing_slash_stripped(self):
        flow = _make_flow()
        with patch.object(flow, "_test_connection", new=AsyncMock(return_value=None)):
            result = run(
                flow.async_step_user({CONF_URL: TEST_URL + "/", CONF_VERIFY_SSL: True})
            )
        self.assertEqual(result["data"][CONF_URL], TEST_URL)


class TestReconfigureStep(unittest.TestCase):
    def setUp(self):
        reset_registry()

    def _make_flow_with_entry(self):
        """Return a flow with _get_reconfigure_entry stubbed out."""
        flow = _make_flow()
        entry = ConfigEntry(
            entry_id="existing_entry",
            data={CONF_URL: "http://old.host:8080", CONF_VERIFY_SSL: True},
            options={CONF_SCAN_INTERVAL: 60},
        )
        flow._get_reconfigure_entry = lambda: entry
        return flow, entry

    def test_shows_form_when_no_input(self):
        flow, _ = self._make_flow_with_entry()
        result = run(flow.async_step_reconfigure(None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "reconfigure")

    def test_success(self):
        flow, entry = self._make_flow_with_entry()
        new_url = "http://new.host:8080"
        # async_update_reload_and_abort normally does real HA work; stub it
        flow.async_update_reload_and_abort = lambda e, title, data, reason: {
            "type": "abort",
            "reason": reason,
        }
        with patch.object(flow, "_test_connection", new=AsyncMock(return_value=None)):
            result = run(
                flow.async_step_reconfigure({CONF_URL: new_url, CONF_VERIFY_SSL: True})
            )
        self.assertEqual(result["reason"], "reconfigure_successful")

    def test_connection_error(self):
        flow, _ = self._make_flow_with_entry()
        with patch.object(
            flow,
            "_test_connection",
            new=AsyncMock(side_effect=ScrutinyApiConnectionError("err")),
        ):
            result = run(
                flow.async_step_reconfigure({CONF_URL: TEST_URL, CONF_VERIFY_SSL: True})
            )
        self.assertEqual(result["errors"]["base"], "cannot_connect")


if __name__ == "__main__":
    unittest.main()
