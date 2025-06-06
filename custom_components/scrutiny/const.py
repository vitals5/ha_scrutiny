"""Constants for the Scrutiny Home Assistant integration."""

from __future__ import (
    annotations,
)  # Ensures compatibility with older Python versions for postponed evaluation of annotations  # noqa: E501

from datetime import timedelta
from logging import Logger, getLogger

# Logger used for the Scrutiny integration.
# getLogger(__package__) ensures that the logger is named after the integration's domain,  # noqa: E501
# which is standard practice in Home Assistant (e.g., "homeassistant.components.scrutiny").  # noqa: E501
LOGGER: Logger = getLogger(__package__)

# The domain of the integration, used as a unique identifier.
# Must match the folder name of the integration.
DOMAIN: str = "scrutiny"

# User-visible name of the integration.
NAME: str = "Scrutiny"

# Version of the integration. Should be kept in sync with manifest.json.
VERSION: str = "0.1.0"

# Configuration keys used in the config flow and config entry data.
CONF_HOST: str = "host"
CONF_PORT: str = "port"

# Default values for configuration.
DEFAULT_PORT: int = 8080  # Default port for the Scrutiny web server.
DEFAULT_SCAN_INTERVAL: timedelta = timedelta(
    minutes=5
)  # Default interval for polling Scrutiny API.

# String keys that correspond to fields in the Scrutiny API response.
# Using constants for these helps avoid typos and makes refactoring easier.
ATTR_DEVICE: str = "device"  # Key for the device details object in API response.
ATTR_SMART: str = "smart"  # Key for the SMART details object in API response.
# ATTR_WWN is not directly used from consts in sensor.py currently,
# the 'wwn' variable is used instead. Keep if planning to use as a const key.
# ATTR_WWN: str = "wwn"  # noqa: ERA001
ATTR_DEVICE_NAME: str = "device_name"  # e.g., "sda", "sdb"
ATTR_MODEL_NAME: str = "model_name"  # e.g., "WDC WD60EFPX-68C5ZN0"
# ATTR_SERIAL_NUMBER is not directly used from consts in sensor.py currently.
# ATTR_SERIAL_NUMBER: str = "serial_number"  # noqa: ERA001
ATTR_FIRMWARE: str = "firmware"  # Firmware version of the disk.
ATTR_CAPACITY: str = "capacity"  # Disk capacity in bytes.
ATTR_DEVICE_STATUS: str = "device_status"  # Overall status code of the disk.
ATTR_TEMPERATURE: str = "temp"  # Current temperature of the disk (from SMART).
ATTR_POWER_ON_HOURS: str = "power_on_hours"  # Total power-on hours (from SMART).

# Mapping of Scrutiny's 'device_status' codes to human-readable strings.
# Based on community feedback and observations of the /api/summary endpoint.
# It's crucial that these accurately reflect the API's meaning for these codes.
SCRUTINY_DEVICE_STATUS_MAP: dict[int, str] = {
    0: "Passed",  # Disk is considered healthy.
    1: "Failed (SMART)",  # Disk has failed a SMART self-test or has critical SMART attr
    2: "Failed (Scrutiny)",
}
# Fallback status string if a status code is unknown or not present.
SCRUTINY_DEVICE_STATUS_UNKNOWN: str = "Unknown"

# List of Home Assistant platforms that this integration will set up.
# Currently, only the "sensor" platform is supported.
PLATFORMS: list[str] = ["sensor"]
