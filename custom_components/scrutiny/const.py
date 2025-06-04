"""Constants for the Scrutiny integration."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

NAME = "Scrutiny"  # Can be used for default titles or other non-translated strings
DOMAIN = "scrutiny"
VERSION = "0.1.0"  # Synchronize with manifest.json

# Configuration and defaults
CONF_HOST = "host"
CONF_PORT = "port"

DEFAULT_PORT = 18080  # Default Scrutiny webserver port
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# Attributes from Scrutiny API that we might use
# These help avoid magic strings in the code
ATTR_DEVICE = "device"
ATTR_SMART = "smart"
ATTR_WWN = "wwn"  # World Wide Name, unique identifier for disks
ATTR_DEVICE_NAME = "device_name"
ATTR_MODEL_NAME = "model_name"
ATTR_SERIAL_NUMBER = "serial_number"
ATTR_FIRMWARE = "firmware"
ATTR_CAPACITY = "capacity"  # API uses "capacity" for bytes
ATTR_DEVICE_STATUS = "device_status"
ATTR_TEMPERATURE = "temp"  # API uses "temp"
ATTR_POWER_ON_HOURS = "power_on_hours"

# Scrutiny device status mapping
# Based on: https://github.com/AnalogJ/scrutiny/blob/master/webapp/backend/pkg/models/device.go

SCRUTINY_DEVICE_STATUS_MAP = {
    0: "Passed",
    1: "Failed SMART Check",
    2: "S.M.A.R.T. Not Supported",
    3: "Disk Not Found",
    # Add more if Scrutiny defines them or if '0' means something else
}
SCRUTINY_DEVICE_STATUS_UNKNOWN = "Unknown"

# Platforms
PLATFORMS = ["sensor"]  # We will support the sensor platform
