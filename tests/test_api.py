"""Tests for ScrutinyApiClient (api.py).

Covers: async_get_summary and async_get_device_details — success paths,
connection errors, auth errors, server errors, wrong content type, and
JSON decode errors.  All tests mock _request so no network is needed.
"""

import asyncio
import json
import os
import sys
import unittest
import unittest.mock
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)

import ha_stubs as stubs

stubs.install()

from custom_components.scrutiny.api import (
    ScrutinyApiAuthError,
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
)
from custom_components.scrutiny.const import (
    ATTR_DEVICE,
    ATTR_METADATA,
    ATTR_SMART,
    ATTR_SMART_RESULTS,
)

run = asyncio.run

TEST_URL = "http://mockhost:1234"

VALID_SUMMARY_RESPONSE = {
    "success": True,
    "data": {
        "summary": {
            "uuid-disk-aaa1": {
                ATTR_DEVICE: {"device_name": "/dev/sda", "model_name": "DiskModelA"},
                ATTR_SMART: {"temp": 30},
            },
            "uuid-disk-bbb2": {
                ATTR_DEVICE: {"device_name": "/dev/sdb", "model_name": "DiskModelB"},
                ATTR_SMART: {"temp": 35},
            },
        }
    },
}

VALID_DETAILS_RESPONSE_DISK1 = {
    "success": True,
    "data": {
        ATTR_DEVICE: {
            "device_name": "/dev/sda",
            "model_name": "DiskModelA",
            "capacity": 1000204886016,
        },
        ATTR_SMART_RESULTS: [
            {
                "attrs": {
                    "5": {"attribute_id": 5, "value": 100, "raw_value": 0},
                    "194": {"attribute_id": 194, "value": 30, "raw_value": 30},
                },
                "Status": 0,
            }
        ],
    },
    ATTR_METADATA: {
        "5": {"display_name": "Reallocated Sectors Count"},
        "194": {"display_name": "Temperature Celsius"},
    },
}


def _make_response(json_data=None, content_type="application/json", text_data=""):
    resp = MagicMock()
    resp.headers = {"Content-Type": content_type}
    resp.raise_for_status = AsyncMock()
    resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value=text_data)
    return resp


def _make_client():
    return ScrutinyApiClient(base_url=TEST_URL, session=MagicMock())


class TestAsyncGetSummary(unittest.TestCase):
    def test_success(self):
        resp = _make_response(json_data=VALID_SUMMARY_RESPONSE)
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            data = run(client.async_get_summary())
        self.assertIn("uuid-disk-aaa1", data)
        self.assertEqual(data["uuid-disk-aaa1"][ATTR_DEVICE]["model_name"], "DiskModelA")
        self.assertEqual(data["uuid-disk-bbb2"][ATTR_SMART]["temp"], 35)

    def test_connection_error(self):
        client = _make_client()
        with unittest.mock.patch.object(
            client,
            "_request",
            new=AsyncMock(side_effect=ScrutinyApiConnectionError("conn")),
        ):
            with self.assertRaises(ScrutinyApiConnectionError):
                run(client.async_get_summary())

    def test_auth_error(self):
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(side_effect=ScrutinyApiAuthError("auth"))
        ):
            with self.assertRaises(ScrutinyApiAuthError):
                run(client.async_get_summary())

    def test_server_error(self):
        client = _make_client()
        with unittest.mock.patch.object(
            client,
            "_request",
            new=AsyncMock(side_effect=ScrutinyApiResponseError("500")),
        ):
            with self.assertRaises(ScrutinyApiResponseError):
                run(client.async_get_summary())

    def test_wrong_content_type(self):
        resp = _make_response(content_type="text/html", text_data="<html/>")
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            with self.assertRaises(ScrutinyApiResponseError) as ctx:
                run(client.async_get_summary())
        self.assertIn("text/html", str(ctx.exception))

    def test_json_decode_error(self):
        resp = _make_response(text_data="not json")
        resp.json = AsyncMock(
            side_effect=json.JSONDecodeError("decode error", "doc", 0)
        )
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            with self.assertRaises(ScrutinyApiResponseError) as ctx:
                run(client.async_get_summary())
        self.assertIn("Invalid JSON", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, json.JSONDecodeError)

    def test_success_false(self):
        resp = _make_response(json_data={"success": False, "message": "error"})
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            with self.assertRaises(ScrutinyApiResponseError):
                run(client.async_get_summary())

    def test_missing_summary_key(self):
        resp = _make_response(json_data={"success": True, "data": {}})
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            with self.assertRaises(ScrutinyApiResponseError):
                run(client.async_get_summary())


class TestAsyncGetDeviceDetails(unittest.TestCase):
    DISK_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_success(self):
        resp = _make_response(json_data=VALID_DETAILS_RESPONSE_DISK1)
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            data = run(client.async_get_device_details(disk_id=self.DISK_ID))
        self.assertTrue(data["success"])
        self.assertIn(ATTR_METADATA, data)
        self.assertEqual(data["data"][ATTR_DEVICE]["model_name"], "DiskModelA")

    def test_connection_error(self):
        client = _make_client()
        with unittest.mock.patch.object(
            client,
            "_request",
            new=AsyncMock(side_effect=ScrutinyApiConnectionError("conn")),
        ):
            with self.assertRaises(ScrutinyApiConnectionError):
                run(client.async_get_device_details(disk_id=self.DISK_ID))

    def test_auth_error(self):
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(side_effect=ScrutinyApiAuthError("auth"))
        ):
            with self.assertRaises(ScrutinyApiAuthError):
                run(client.async_get_device_details(disk_id=self.DISK_ID))

    def test_server_error(self):
        client = _make_client()
        with unittest.mock.patch.object(
            client,
            "_request",
            new=AsyncMock(side_effect=ScrutinyApiResponseError("500")),
        ):
            with self.assertRaises(ScrutinyApiResponseError):
                run(client.async_get_device_details(disk_id=self.DISK_ID))

    def test_wrong_content_type(self):
        resp = _make_response(content_type="text/plain", text_data="nope")
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            with self.assertRaises(ScrutinyApiResponseError) as ctx:
                run(client.async_get_device_details(disk_id=self.DISK_ID))
        self.assertIn("text/plain", str(ctx.exception))

    def test_json_decode_error(self):
        resp = _make_response(text_data="bad json")
        resp.json = AsyncMock(
            side_effect=json.JSONDecodeError("decode error", "doc", 0)
        )
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            with self.assertRaises(ScrutinyApiResponseError) as ctx:
                run(client.async_get_device_details(disk_id=self.DISK_ID))
        self.assertIn("Invalid JSON", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, json.JSONDecodeError)

    def test_success_false(self):
        resp = _make_response(json_data={"success": False, "message": "fail"})
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            with self.assertRaises(ScrutinyApiResponseError) as ctx:
                run(client.async_get_device_details(disk_id=self.DISK_ID))
        self.assertIn("not successful", str(ctx.exception))

    def test_missing_data_key(self):
        resp = _make_response(
            json_data={"success": True, ATTR_METADATA: {"key": "val"}}
        )
        client = _make_client()
        with unittest.mock.patch.object(
            client, "_request", new=AsyncMock(return_value=resp)
        ):
            with self.assertRaises(ScrutinyApiResponseError) as ctx:
                run(client.async_get_device_details(disk_id=self.DISK_ID))
        self.assertIn("missing", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
