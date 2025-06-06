"""Constants for the Scrutiny integration."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

NAME = "Scrutiny"
DOMAIN = "scrutiny"
VERSION = "0.1.0"  # Synchronize with manifest.json

# Configuration and defaults
CONF_HOST = "host"
CONF_PORT = "port"

DEFAULT_PORT = 18080
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# Attributes from Scrutiny API
ATTR_DEVICE = "device"
ATTR_SMART = "smart"
ATTR_DEVICE_NAME = "device_name"
ATTR_MODEL_NAME = "model_name"
ATTR_FIRMWARE = "firmware"
ATTR_CAPACITY = "capacity"
ATTR_DEVICE_STATUS = "device_status"
ATTR_TEMPERATURE = "temp"
ATTR_POWER_ON_HOURS = "power_on_hours"

# Scrutiny device status mapping for 'device_status' from /api/summary
# Based on your latest information:
# 0 = Passed
# 1 = Failed SMART
# 2 = Failed Scrutiny
SCRUTINY_DEVICE_STATUS_MAP = {
    0: "Passed",
    1: "Failed (S.M.A.R.T.)",  # Präzisiert, da es spezifisch SMART-Fehler sind
    2: "Failed (Scrutiny)",  # Neuer Status
}
SCRUTINY_DEVICE_STATUS_UNKNOWN = "Unknown"

# Platforms
PLATFORMS = ["sensor"]
