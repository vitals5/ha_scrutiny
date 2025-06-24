"""Constants for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from datetime import timedelta
from logging import Logger, getLogger

# Logger instance for the integration.
LOGGER: Logger = getLogger(__package__)

# Domain of the integration, used by Home Assistant.
DOMAIN: str = "scrutiny"
# User-visible name of the integration. Also used as default manufacturer for devices.
NAME: str = "Scrutiny"
# Version of the integration.
VERSION: str = "0.3.3"

# Configuration keys used in config_flow.py and __init__.py.
CONF_HOST: str = "host"  # Key for the Scrutiny server host.
CONF_PORT: str = "port"  # Key for the Scrutiny server port.
CONF_SCAN_INTERVAL: str = "scan_interval"  # Key for the poll interval for data updates.
# Default values for configuration.
DEFAULT_PORT: int = 8080  # Default port for the Scrutiny API.
DEFAULT_SCAN_INTERVAL_MINUTES: int = 60  # Default polling interval in minutes.
DEFAULT_SCAN_INTERVAL: timedelta = timedelta(
    minutes=DEFAULT_SCAN_INTERVAL_MINUTES
)  # Default interval for polling data.

# --- Keys for navigating the aggregated data structure in the coordinator ---
# These keys are used internally by the coordinator to structure the data fetched
# from the Scrutiny API and by sensor.py to access specific parts of this data.
# For example, coordinator.data[wwn][KEY_SUMMARY_DEVICE] would access
# the device summary for a disk with a given WWN.

# Key for the 'device' part of the summary data for a disk.
KEY_SUMMARY_DEVICE: str = "summary_device"
# Key for the 'smart' part of the summary data for a disk.
KEY_SUMMARY_SMART: str = "summary_smart"
# Key for the 'device' part of the detailed data for a disk.
KEY_DETAILS_DEVICE: str = "details_device"
# Key for the latest SMART snapshot from the detailed data for a disk.
KEY_DETAILS_SMART_LATEST: str = "details_smart_latest"
# Key for the metadata of SMART attributes from the detailed data for a disk.
KEY_DETAILS_METADATA: str = "details_smart_attributes_metadata"


# --- Attribute Keys from Scrutiny API responses ---
# These constants map to the field names found in the JSON responses
# from the Scrutiny API.

# Keys for general disk information
#  (often present in both summary and details API responses).
# ATTR_WWN is the World Wide Name, used as the primary identifier for disks.
# It's also a field within the device object from the API.
ATTR_WWN: str = "wwn"  # World Wide Name of the disk.
ATTR_DEVICE_NAME: str = "device_name"  # e.g., /dev/sda
ATTR_MODEL_NAME: str = "model_name"  # e.g., "Samsung SSD 860 EVO"
ATTR_FIRMWARE: str = "firmware"  # Firmware version of the disk.
ATTR_CAPACITY: str = "capacity"  # Disk capacity in bytes.
ATTR_SERIAL_NUMBER: str = "serial_number"  # Serial number of the disk.

# Keys specifically from the '/api/summary' -> 'device' object of a disk.
ATTR_SUMMARY_DEVICE_STATUS: str = (
    "device_status"  # Overall status of the device from the summary.
)

# Keys from SMART data, potentially found
#  in both summary and/or latest details snapshot.
ATTR_TEMPERATURE: str = "temp"  # Current temperature of the disk (often in Celsius).
ATTR_POWER_ON_HOURS: str = "power_on_hours"  # Total power-on hours for the disk.
ATTR_POWER_CYCLE_COUNT: str = (
    "power_cycle_count"  # Number of power cycles. (From details_smart_latest)
)

# Keys related to the structure of the '/api/device/{wwn}/details' API response.
ATTR_DEVICE: str = "device"  # The 'device' object within the details payload.
ATTR_SMART_RESULTS: str = (
    "smart_results"  # Array of SMART snapshots in the details payload.
)
ATTR_METADATA: str = "metadata"  # Metadata for SMART attributes in the details payload.

# Keys within a single SMART snapshot (e.g., smart_results[0] from details).
ATTR_SMART_ATTRS: str = "attrs"  # Dictionary of individual SMART attributes.
ATTR_SMART_OVERALL_STATUS: str = (
    "Status"  # Overall SMART status for this snapshot (Note: Capital 'S').
)
ATTR_SMART: str = (
    "smart"  # Key for the 'smart' object within the summary payload for a disk.
)

# Keys within each individual SMART attribute object
# (e.g., smart_results[0].attrs[<attribute_id_str>]).
ATTR_ATTRIBUTE_ID: str = (
    "attribute_id"  # Numeric ID of the SMART attribute (e.g., 5, 194).
)
ATTR_NORMALIZED_VALUE: str = "value"  # Current normalized value of the SMART attribute.
ATTR_THRESH: str = "thresh"  # Threshold value for the SMART attribute.
ATTR_WORST: str = "worst"  # Worst recorded normalized value for the SMART attribute.
ATTR_RAW_VALUE: str = "raw_value"  # Raw value of the SMART attribute.
ATTR_RAW_STRING: str = "raw_string"  # Raw value as a string, often more human-readable.
ATTR_WHEN_FAILED: str = (
    "when_failed"  # Indicates when/if the attribute failed (e.g., "-", "FAILING_NOW").
)
# Status code of a single SMART attribute (e.g., 0 for Passed, 1 for Failed).
ATTR_SMART_ATTRIBUTE_STATUS_CODE: str = "status"
ATTR_FAILURE_RATE: str = "failure_rate"  # Predicted failure rate, if available.
ATTR_STATUS_REASON: str = (
    "status_reason"  # Reason for the current status of the attribute.
)

# Keys within ATTR_METADATA (metadata for each SMART attribute_id).
ATTR_DISPLAY_NAME: str = (
    "display_name"  # Human-readable name (e.g., "Reallocated Sectors Count").
)
ATTR_IDEAL_VALUE_DIRECTION: str = (
    "ideal"  # Direction of ideal values (e.g., "low", "high", "").
)
ATTR_IS_CRITICAL: str = (
    "critical"  # Boolean: true if the attribute is considered critical.
)
ATTR_DESCRIPTION: str = "description"  # Text description of the SMART attribute.

# --- Status Mappings ---

# Mapping for 'device_status' from the '/api/summary' endpoint.
SCRUTINY_DEVICE_SUMMARY_STATUS_MAP: dict[int, str] = {
    0: "Passed",  # Device is considered healthy.
    1: "Failed (S.M.A.R.T.)",  # Device failed due to SMART attributes.
    2: "Failed (Scrutiny)",  # Device failed based on Scrutiny's own checks.
}
SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN: str = (
    "Unknown Summary Status"  # Fallback for unknown status codes.
)

# Mapping for the 'status' of individual SMART attributes
# from '/api/device/.../details' -> smart_results[0].attrs[id].status.
ATTR_SMART_STATUS_MAP: dict[int, str] = {
    0: "Passed",  # Attribute is within normal parameters.
    1: "Failed (S.M.A.R.T.)",  # Attribute has failed according to S.M.A.R.T.
    2: "Warning (Scrutiny)",  # Scrutiny has issued a warning for this attribute.
    4: "Failed (Scrutiny)",  # Scrutiny has marked this attribute as failed.
}
ATTR_SMART_STATUS_UNKNOWN: str = (
    "Unknown Attribute Status"  # Fallback for unknown attribute status codes.
)


# Platforms to set up for this integration (e.g., "sensor", "binary_sensor").
PLATFORMS: list[str] = ["sensor"]
