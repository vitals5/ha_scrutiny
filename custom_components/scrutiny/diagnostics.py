"""Diagnostics support for the Scrutiny integration."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import ScrutinyConfigEntry
from .const import (
    ATTR_DEVICE_NAME,
    ATTR_FIRMWARE,
    ATTR_MODEL_NAME,
    ATTR_POWER_ON_HOURS,
    ATTR_SERIAL_NUMBER,
    ATTR_SMART_ATTRS,
    ATTR_SMART_OVERALL_STATUS,
    ATTR_TEMPERATURE,
    ATTR_WWN,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_VERIFY_SSL,
    KEY_DETAILS_METADATA,
    KEY_DETAILS_SMART_LATEST,
    KEY_SUMMARY_DEVICE,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ScrutinyConfigEntry,
) -> dict[str, Any]:
    """
    Return diagnostics for a Scrutiny config entry.

    Provides the server URL, coordinator state, and a per-disk summary
    suitable for bug reports without exposing raw SMART attribute data in bulk.
    """
    coordinator = entry.runtime_data

    disks: list[dict[str, Any]] = []
    if coordinator.data:
        for disk_id, disk_data in coordinator.data.items():
            summary_device: dict[str, Any] = disk_data.get(KEY_SUMMARY_DEVICE, {})
            smart_latest: dict[str, Any] = disk_data.get(KEY_DETAILS_SMART_LATEST, {})
            metadata: dict[str, Any] = disk_data.get(KEY_DETAILS_METADATA, {})

            disks.append(
                {
                    "scrutiny_disk_id": disk_id,
                    "wwn": summary_device.get(ATTR_WWN),
                    "serial_number": summary_device.get(ATTR_SERIAL_NUMBER),
                    "device_name": summary_device.get(ATTR_DEVICE_NAME),
                    "model": summary_device.get(ATTR_MODEL_NAME),
                    "firmware": summary_device.get(ATTR_FIRMWARE),
                    "device_status": summary_device.get("device_status"),
                    "temperature": smart_latest.get(ATTR_TEMPERATURE),
                    "power_on_hours": smart_latest.get(ATTR_POWER_ON_HOURS),
                    "smart_status": smart_latest.get(ATTR_SMART_OVERALL_STATUS),
                    "smart_attribute_count": len(
                        smart_latest.get(ATTR_SMART_ATTRS, {})
                    ),
                    "metadata_attribute_count": len(metadata),
                }
            )

    return {
        "config_entry": {
            "url": entry.data.get(CONF_URL),
            "verify_ssl": entry.data.get(CONF_VERIFY_SSL),
            "scan_interval": entry.options.get(CONF_SCAN_INTERVAL),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "disk_count": len(coordinator.data) if coordinator.data else 0,
        },
        "disks": disks,
    }
