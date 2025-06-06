"""Constants for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN: str = "scrutiny"
NAME: str = "Scrutiny"  # User-visible name, also used for default manufacturer
VERSION: str = "0.1.0"

# Configuration keys
CONF_HOST: str = "host"
CONF_PORT: str = "port"

# Default values
DEFAULT_PORT: int = 8080
DEFAULT_SCAN_INTERVAL: timedelta = timedelta(minutes=5)

# --- Keys for navigating the aggregated data structure in the coordinator ---
# These are used in sensor.py to access specific parts of the data
# that the coordinator prepares (e.g., coordinator.data[wwn][KEY_SUMMARY_DEVICE])
KEY_SUMMARY_DEVICE: str = "summary_device"
KEY_SUMMARY_SMART: str = "summary_smart"
KEY_DETAILS_DEVICE: str = "details_device"
KEY_DETAILS_SMART_LATEST: str = "details_smart_latest"
KEY_DETAILS_METADATA: str = "details_smart_attributes_metadata"


# --- Attribute Keys from Scrutiny API responses ---

# Keys for general disk information (often from both summary and details)
# ATTR_WWN is used as the primary key for disks in our data structures.
# It's also a field within the device object from the API.
ATTR_WWN: str = (
    "wwn"  # Retained for clarity, even if 'wwn' variable is often used directly
)
ATTR_DEVICE_NAME: str = "device_name"
ATTR_MODEL_NAME: str = "model_name"
ATTR_FIRMWARE: str = "firmware"
ATTR_CAPACITY: str = "capacity"  # In bytes, from summary and details device sections
ATTR_SERIAL_NUMBER: str = "serial_number"  # Added back, can be useful for DeviceInfo

# Keys specifically from the '/api/summary' -> 'device' object
ATTR_SUMMARY_DEVICE_STATUS: str = (
    "device_status"  # The 'device_status' field from the summary
)

# Keys from SMART data (summary and/or latest details snapshot)
ATTR_TEMPERATURE: str = "temp"
ATTR_POWER_ON_HOURS: str = "power_on_hours"
ATTR_POWER_CYCLE_COUNT: str = "power_cycle_count"  # From details_smart_latest

# Keys related to the structure of '/api/device/{wwn}/details' response
ATTR_DEVICE: str = "device"  # The 'device' object within the details payload
ATTR_SMART_RESULTS: str = "smart_results"  # Array of SMART snapshots in details
ATTR_METADATA: str = "metadata"  # Metadata for SMART attributes in details

# Keys within smart_results[0] (latest SMART snapshot from details)
ATTR_SMART_ATTRS: str = "attrs"  # The dictionary of individual SMART attributes
ATTR_SMART_OVERALL_STATUS: str = (
    "Status"  # Capital 'S', overall status for this SMART snapshot
)
ATTR_SMART: str = "smart"  # Key for smart overview in summary
# Keys within each individual SMART attribute object
# (e.g., smart_results[0].attrs[ATTR_ATTRIBUTE_ID])
ATTR_ATTRIBUTE_ID: str = "attribute_id"
ATTR_NORMALIZED_VALUE: str = (
    "value"  # Renamed from ATTR_VALUE to avoid conflict with general 'value'
)
ATTR_THRESH: str = "thresh"
ATTR_WORST: str = "worst"
ATTR_RAW_VALUE: str = "raw_value"
ATTR_RAW_STRING: str = "raw_string"
ATTR_WHEN_FAILED: str = "when_failed"
ATTR_SMART_ATTRIBUTE_STATUS_CODE: str = (
    "status"  # Status code of a single SMART attr (0, 1, 2, 4)
)
ATTR_FAILURE_RATE: str = "failure_rate"
ATTR_STATUS_REASON: str = "status_reason"

# Keys within ATTR_METADATA (for each attribute_id)
ATTR_DISPLAY_NAME: str = "display_name"  # e.g., "Reallocated Sectors Count"
ATTR_IDEAL_VALUE_DIRECTION: str = "ideal"  # e.g., "low", "high", ""
ATTR_IS_CRITICAL: str = "critical"  # boolean: true if attribute is critical
ATTR_DESCRIPTION: str = "description"  # Text description of the attribute

# --- Status Mappings ---

# For 'device_status' from /api/summary
SCRUTINY_DEVICE_SUMMARY_STATUS_MAP: dict[int, str] = {
    0: "Passed",
    1: "Failed (SMART)",
    2: "Failed (Scrutiny)",
}
SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN: str = "Unknown Summary Status"

# For 'status' of individual SMART attributes from /api/device/.../details
# -> smart_results[0].attrs[id].status
ATTR_SMART_STATUS_MAP: dict[int, str] = {
    0: "Passed",
    1: "Failed (S.M.A.R.T.)",
    2: "Warning (Scrutiny)",
    4: "Failed (Scrutiny)",
}
ATTR_SMART_STATUS_UNKNOWN: str = "Unknown Attribute Status"


# Platforms to set up
PLATFORMS: list[str] = ["sensor"]
