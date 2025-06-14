"""Sensor platform for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,  # Enum for device classes (e.g., TEMPERATURE, HUMIDITY)
    SensorEntity,  # Base class for sensor entities
    SensorEntityDescription,  # Describes a sensor entity's properties
    SensorStateClass,  # Enum for state classes (e.g., MEASUREMENT, TOTAL_INCREASING)
)
from homeassistant.const import (
    EntityCategory,  # Enum for entity categories (e.g., DIAGNOSTIC, CONFIG)
    UnitOfInformation,  # Units for information (e.g., GIGABYTES)
    UnitOfTemperature,  # Units for temperature (e.g., CELSIUS)
    UnitOfTime,  # Units for time (e.g., HOURS)
)
from homeassistant.helpers.device_registry import (
    DeviceInfo,
)  # For defining device properties
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)  # Base for entities using a coordinator
from homeassistant.util import slugify  # Utility to create URL-friendly slugs

# Import constants from the integration's const.py
from .const import (
    ATTR_ATTRIBUTE_ID,
    ATTR_CAPACITY,
    ATTR_DESCRIPTION,
    ATTR_DEVICE_NAME,
    ATTR_DISPLAY_NAME,
    ATTR_FAILURE_RATE,
    ATTR_FIRMWARE,
    ATTR_IDEAL_VALUE_DIRECTION,
    ATTR_IS_CRITICAL,
    ATTR_MODEL_NAME,
    ATTR_NORMALIZED_VALUE,
    ATTR_POWER_CYCLE_COUNT,
    ATTR_POWER_ON_HOURS,
    ATTR_RAW_STRING,
    ATTR_RAW_VALUE,
    ATTR_SMART_ATTRIBUTE_STATUS_CODE,
    ATTR_SMART_ATTRS,
    ATTR_SMART_OVERALL_STATUS,
    ATTR_SMART_STATUS_MAP,
    ATTR_SMART_STATUS_UNKNOWN,
    ATTR_STATUS_REASON,
    ATTR_SUMMARY_DEVICE_STATUS,
    ATTR_TEMPERATURE,
    ATTR_THRESH,
    ATTR_WHEN_FAILED,
    ATTR_WORST,
    DOMAIN,  # The integration's domain
    KEY_DETAILS_METADATA,  # Key for SMART attribute metadata in coordinator data
    KEY_DETAILS_SMART_LATEST,  # Key for latest SMART details in coordinator data
    KEY_SUMMARY_DEVICE,  # Key for device summary in coordinator data
    KEY_SUMMARY_SMART,  # Key for SMART summary in coordinator data
    LOGGER,  # The integration's logger
    SCRUTINY_DEVICE_SUMMARY_STATUS_MAP,  # Mapping for overall device status
    SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN,  # Fallback for unknown device status
)
from .const import (
    NAME as INTEGRATION_NAME,  # User-visible name of the integration
)

# Import the data update coordinator
from .coordinator import ScrutinyDataUpdateCoordinator

# Conditional import for type checking
if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import ScrutinyConfigEntry  # Type hint for the config entry


# Descriptions for the main sensors created for each disk.
# Each SensorEntityDescription defines properties for a specific sensor type.
MAIN_DISK_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_TEMPERATURE,  # Corresponds to the key in Scrutiny data
        name="Temperature",  # Default name for this sensor type
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        # Value represents a current measurement
        state_class=SensorStateClass.MEASUREMENT,
        # Sensor provides diagnostic info
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_POWER_ON_HOURS,
        name="Power On Hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:timer-sand",
        # Value is a monotonically increasing total
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        # This key refers to the overall status from summary
        key=ATTR_SUMMARY_DEVICE_STATUS,
        name="Overall Device Status",
        icon="mdi:harddisk",
        # Sensor state is one of a predefined set of strings
        device_class=SensorDeviceClass.ENUM,
        options=[  # Possible string values for this ENUM sensor
            *SCRUTINY_DEVICE_SUMMARY_STATUS_MAP.values(),
            SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN,
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_CAPACITY,
        name="Capacity",
        # Will be converted from bytes
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        icon="mdi:database",
        state_class=SensorStateClass.MEASUREMENT,
        # Display with 2 decimal places
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_POWER_CYCLE_COUNT,
        name="Power Cycle Count",
        icon="mdi:autorenew",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        # This key refers to the SMART test result from details
        key=ATTR_SMART_OVERALL_STATUS,
        name="SMART Test Result",
        icon="mdi:shield-check-outline",
        device_class=SensorDeviceClass.ENUM,
        options=[*ATTR_SMART_STATUS_MAP.values(), ATTR_SMART_STATUS_UNKNOWN],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - hass is not directly used but required by the signature
    entry: ScrutinyConfigEntry,  # The config entry for this integration instance
    async_add_entities: AddEntitiesCallback,  # Callback to add entities to Home Assist
) -> None:
    """Set up Scrutiny sensor entities from a config entry."""
    # Retrieve the coordinator instance stored in the config entry's runtime_data.
    coordinator: ScrutinyDataUpdateCoordinator = entry.runtime_data

    # If the coordinator has no data yet (e.g., first update failed or no disks found),
    # log it and skip sensor setup for now. Sensors might be set up on a later update.
    if not coordinator.data:
        LOGGER.info(
            "No disk data from Scrutiny coordinator for %s; "
            "sensor setup skipped for now.",
            entry.title,
        )
        return

    entities_to_add: list[
        SensorEntity
    ] = []  # List to collect all sensor entities to be added

    # Iterate over each disk (identified by WWN) found by the coordinator.
    # coordinator.data is a dict:
    #  {wwn: {KEY_SUMMARY_DEVICE: ..., KEY_DETAILS_SMART_LATEST: ...}}  # noqa: ERA001
    for wwn, aggregated_disk_data in coordinator.data.items():
        # Extract relevant parts of the aggregated data for this disk.
        summary_device_data = aggregated_disk_data.get(KEY_SUMMARY_DEVICE, {})
        details_smart_latest = aggregated_disk_data.get(KEY_DETAILS_SMART_LATEST, {})
        details_metadata = aggregated_disk_data.get(KEY_DETAILS_METADATA, {})

        # Create DeviceInfo for this disk. All sensors related
        #  to this disk will be associated with this device.
        device_info_name = (
            # Use model name or "Disk"
            f"{summary_device_data.get(ATTR_MODEL_NAME, 'Disk')} "
            # Use device name or last 6 chars of WWN
            f"({summary_device_data.get(ATTR_DEVICE_NAME, wwn[-6:])})"
        )
        device_info = DeviceInfo(
            identifiers={(DOMAIN, wwn)},  # Unique identifier for this device (WWN)
            name=device_info_name,
            model=summary_device_data.get(ATTR_MODEL_NAME),
            manufacturer=summary_device_data.get("manufacturer")
            or INTEGRATION_NAME,  # Use Scrutiny's manufacturer or integration name
            sw_version=summary_device_data.get(ATTR_FIRMWARE),
            via_device=(
                DOMAIN,
                entry.entry_id,
            ),  # Link to the "hub" device created in __init__.py
        )

        # Create the main disk sensors (Temperature, Power On Hours, etc.) for this disk
        entities_to_add.extend(
            [
                ScrutinyMainDiskSensor(
                    coordinator=coordinator,
                    # From MAIN_DISK_SENSOR_DESCRIPTIONS
                    entity_description=description,
                    wwn=wwn,
                    device_info=device_info,
                )
                for description in MAIN_DISK_SENSOR_DESCRIPTIONS
            ]
        )

        # Create sensors for individual SMART attributes of this disk.
        # ATTR_SMART_ATTRS is the key for the dictionary of
        #  SMART attributes within details_smart_latest.
        smart_attributes_data = details_smart_latest.get(ATTR_SMART_ATTRS, {})
        if isinstance(smart_attributes_data, dict):
            # smart_attributes_data is like:
            #  {"5": {attribute_id:5, value:100, ...}, "194": {...}}
            for attr_id_str_key, attr_data_value in smart_attributes_data.items():
                if not isinstance(attr_data_value, dict):
                    LOGGER.warning(
                        (
                            "Skipping SMART attribute %s for disk %s: "
                            "unexpected data format %s"
                        ),
                        attr_id_str_key,
                        wwn,
                        type(attr_data_value),
                    )
                    continue

                # ATTR_ATTRIBUTE_ID is the numeric ID
                #  (e.g., 5), attr_id_str_key is its string version.
                numeric_attr_id = attr_data_value.get(ATTR_ATTRIBUTE_ID)
                if numeric_attr_id is None:
                    LOGGER.warning(
                        (
                            "SMART attribute for disk %s (key %s) "
                            "is missing '%s'. Data: %s"
                        ),
                        wwn,
                        attr_id_str_key,
                        ATTR_ATTRIBUTE_ID,
                        attr_data_value,
                    )
                    continue

                actual_attribute_id_for_sensor = str(numeric_attr_id)

                # Get metadata for this specific attribute ID from the details_metadata.
                # The keys in details_metadata are
                #  string representations of numeric_attr_id.
                attr_metadata = details_metadata.get(actual_attribute_id_for_sensor, {})

                LOGGER.debug(
                    "ASYNC_SETUP_ENTRY (WWN: %s, AttrID_str: %s, NumID: %s): "
                    "Passing to SENSOR constructor-> attribute_metadata: %s (Type: %s)",
                    wwn,
                    attr_id_str_key,
                    numeric_attr_id,
                    str(attr_metadata)[:500],  # Log a part of the metadata
                    type(attr_metadata),
                )

                entities_to_add.append(
                    ScrutinySmartAttributeSensor(
                        coordinator=coordinator,
                        wwn=wwn,
                        device_info=device_info,
                        # The string key like "5", "194"
                        attribute_id_str=actual_attribute_id_for_sensor,
                        # Metadata for this attribute
                        attribute_metadata=attr_metadata,
                    )
                )
        else:
            LOGGER.warning(
                (
                    "SMART attributes data for disk %s is not a dict: "
                    "%s. Skipping SMART attribute sensors."
                ),
                wwn,
                type(smart_attributes_data),
            )

    # Add all collected entities to Home Assistant.
    if entities_to_add:
        async_add_entities(entities_to_add)


class ScrutinyMainDiskSensor(
    CoordinatorEntity[ScrutinyDataUpdateCoordinator], SensorEntity
):
    """Representation of a main sensor for a Scrutiny-monitored disk (Temp, POH)."""

    _attr_has_entity_name = (
        True  # The entity's name is derived from entity_description.name
    )
    _attr_entity_category = (
        EntityCategory.DIAGNOSTIC
    )  # Default category for these sensors

    def __init__(
        self,
        coordinator: ScrutinyDataUpdateCoordinator,
        entity_description: SensorEntityDescription,  # Defines key, name, units, etc.
        wwn: str,  # WWN of the disk this sensor belongs to
        device_info: DeviceInfo,  # DeviceInfo for the parent disk
    ) -> None:
        """Initialize the main disk sensor."""
        super().__init__(coordinator)  # Initialize CoordinatorEntity
        self.entity_description = entity_description  # Store the description
        self._wwn = wwn  # Store the disk's WWN
        self._attr_device_info = device_info  # Associate with the disk's device
        # Create a unique ID for this sensor entity.
        self._attr_unique_id = f"{DOMAIN}_{self._wwn}_{self.entity_description.key}"
        # Initial update of sensor state based on current coordinator data.
        self._update_sensor_state()

    @property
    def available(self) -> bool:
        """Return True if the sensor's data is available from the coordinator."""
        return (
            super().available  # Check availability from CoordinatorEntity
            and self.coordinator.data is not None
            and self._wwn in self.coordinator.data  # Check if data for this WWN exists
            # Ensure the necessary summary data key exists,
            #  as most main sensors rely on it.
            and KEY_SUMMARY_DEVICE in self.coordinator.data[self._wwn]
        )

    def _update_sensor_state(self) -> None:
        """Update the sensor's state (native_value) from coordinator data."""
        if not self.available:
            self._attr_native_value = None  # Set to None if unavailable
            return

        # Get the aggregated data for this disk (WWN)
        data = self.coordinator.data[self._wwn]
        # Extract specific parts of the data
        summary_device_data = data.get(KEY_SUMMARY_DEVICE, {})
        summary_smart_data = data.get(KEY_SUMMARY_SMART, {})
        details_smart_latest = data.get(KEY_DETAILS_SMART_LATEST, {})

        key = (
            self.entity_description.key
        )  # The key defining what this sensor represents (e.g., ATTR_TEMPERATURE)
        value = None  # Initialize value to None

        # Determine the sensor's value based on its key.
        # Some values might be in details, with a fallback to summary if not present.
        if key == ATTR_TEMPERATURE:
            value = details_smart_latest.get(
                ATTR_TEMPERATURE, summary_smart_data.get(ATTR_TEMPERATURE)
            )
        elif key == ATTR_POWER_ON_HOURS:
            value = details_smart_latest.get(
                ATTR_POWER_ON_HOURS, summary_smart_data.get(ATTR_POWER_ON_HOURS)
            )
        elif key == ATTR_SUMMARY_DEVICE_STATUS:
            status_code = summary_device_data.get(ATTR_SUMMARY_DEVICE_STATUS)
            # Map the status code to a human-readable string.
            value = (
                SCRUTINY_DEVICE_SUMMARY_STATUS_MAP.get(
                    status_code, SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN
                )
                if status_code is not None
                else SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN
            )
        elif key == ATTR_CAPACITY:
            capacity_bytes = summary_device_data.get(ATTR_CAPACITY)
            if capacity_bytes is not None:
                # Convert capacity from bytes to gigabytes.
                value = round(capacity_bytes / (1024**3), 2)
        elif key == ATTR_POWER_CYCLE_COUNT:
            # This value is typically only in detailed SMART data.
            value = details_smart_latest.get(ATTR_POWER_CYCLE_COUNT)
        elif key == ATTR_SMART_OVERALL_STATUS:
            # This status comes from the 'Status' field in the latest SMART snapshot.
            status_code = details_smart_latest.get(ATTR_SMART_OVERALL_STATUS)
            value = (
                ATTR_SMART_STATUS_MAP.get(status_code, ATTR_SMART_STATUS_UNKNOWN)
                if status_code is not None
                else ATTR_SMART_STATUS_UNKNOWN
            )
        # Set the sensor's native value.
        self._attr_native_value = value

    def _handle_coordinator_update(self) -> None:
        """
        Handle updated data from the coordinator.
        This method is called by CoordinatorEntity
        when the coordinator signals new data.
        """  # noqa: D205
        self._update_sensor_state()  # Re-calculate the sensor's state
        self.async_write_ha_state()  # Schedule an update to Home Assistant


class ScrutinySmartAttributeSensor(
    CoordinatorEntity[ScrutinyDataUpdateCoordinator], SensorEntity
):
    """Representation of a single SMART attribute for a Scrutiny-monitored disk."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC  # These are diagnostic sensors
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ScrutinyDataUpdateCoordinator,
        wwn: str,  # WWN of the parent disk
        device_info: DeviceInfo,  # DeviceInfo of the parent disk
        # String representation of the SMART attribute ID (e.g., "5", "194")
        attribute_id_str: str,
        attribute_metadata: dict[
            str, Any
        ],  # Metadata for this attribute (name, description, etc.)
    ) -> None:
        """Initialize the SMART attribute sensor."""
        super().__init__(coordinator)
        self._wwn = wwn
        self._attribute_id_str = attribute_id_str  # e.g., "5", "194"
        self._attribute_metadata = (
            attribute_metadata  # e.g., {"display_name": "Reallocated Sector Ct", ...}
        )
        self._attr_device_info = device_info  # Associate with the disk's device

        LOGGER.debug(
            "SMART ATTR INIT (WWN: %s, AttrID_str: %s): Full Metadata received: %s",
            wwn,
            attribute_id_str,
            attribute_metadata,
        )

        # Get the display name from metadata, e.g., "Reallocated Sectors Count".
        display_name_meta = self._attribute_metadata.get(ATTR_DISPLAY_NAME)
        attribute_specific_name_part = (
            display_name_meta
            if display_name_meta
            else f"Attribute {self._attribute_id_str}"
        )

        LOGGER.debug(
            (
                "SMART ATTR INIT (WWN: %s, AttrID_str: %s): "
                "Extracted display_name_meta: %s (Type: %s)"
            ),
            wwn,
            attribute_id_str,
            display_name_meta,
            type(display_name_meta),
        )

        # Define the entity description for this SMART attribute sensor.
        # The state of this sensor will be the status
        #  of the SMART attribute (e.g., "Passed", "Failed").
        self.entity_description = SensorEntityDescription(
            key=f"smart_attr_{self._attribute_id_str}",
            name=f"SMART {self._attribute_id_str} {attribute_specific_name_part}",
            device_class=SensorDeviceClass.ENUM,
            options=[*ATTR_SMART_STATUS_MAP.values(), ATTR_SMART_STATUS_UNKNOWN],
        )

        # Create a unique ID for this sensor entity.
        # Slugify the name part to ensure it's URL-friendly and consistent.
        summary_device_data = coordinator.data.get(wwn, {}).get(KEY_SUMMARY_DEVICE, {})
        device_name_raw = summary_device_data.get(ATTR_DEVICE_NAME)
        if not device_name_raw:
            device_name_cleaned_for_id = f"disk_{wwn[-6:]}"
        else:
            device_name_cleaned_for_id = device_name_raw.split("/")[-1]
        device_name_slug_for_id = slugify(device_name_cleaned_for_id)

        slugified_attr_name_part_for_id = slugify(attribute_specific_name_part)

        self._attr_unique_id = (
            f"{DOMAIN}_{self._wwn}_{device_name_slug_for_id}_smart_"
            f"{self._attribute_id_str}_{slugified_attr_name_part_for_id}"
        )

        LOGGER.debug(
            "SMART ATTR INIT (WWN: %s, AttrID_str: %s): Final unique_id: %s",
            wwn,
            attribute_id_str,
            self._attr_unique_id,
        )

        # Critical attributes sensors should be enabled by default.
        is_critical_attribute = self._attribute_metadata.get(ATTR_IS_CRITICAL, False)
        self._attr_entity_registry_enabled_default = bool(is_critical_attribute)

        # Initial update of state and attributes.
        self._update_state_and_attributes()

    @property
    def available(self) -> bool:
        """Return True if the sensor's data is available from the coordinator."""
        if not (
            super().available  # Check base CoordinatorEntity availability
            and self.coordinator.data is not None
            and self._wwn in self.coordinator.data  # Data for this disk exists
        ):
            return False

        # Check if the detailed SMART data and specific attribute exist.
        disk_agg_data = self.coordinator.data[self._wwn]
        latest_smart = disk_agg_data.get(KEY_DETAILS_SMART_LATEST)
        if not isinstance(latest_smart, dict):
            return False

        attrs = latest_smart.get(ATTR_SMART_ATTRS)
        if not isinstance(attrs, dict):
            return False

        # True if this specific attribute ID
        #  (e.g., "5") is in the SMART attributes dict.
        return self._attribute_id_str in attrs

    def _get_current_attribute_data(self) -> dict[str, Any] | None:
        """
        Safely retrieve the current data for this specific SMART attribute
        from the coordinator's data.

        Returns:
            A dictionary containing the data for this SMART
            attribute, or None if not available.

        """  # noqa: D205
        if not self.available:
            return None
        # If available is true, this path should be safe due to checks in
        #  `available` property.
        # self.coordinator.data[self._wwn] -> aggregated data for the disk
        # [KEY_DETAILS_SMART_LATEST] -> latest SMART snapshot for the disk
        # [ATTR_SMART_ATTRS] -> dictionary of all SMART attributes
        # .get(self._attribute_id_str) -> data for this specific attribute
        return self.coordinator.data[self._wwn][KEY_DETAILS_SMART_LATEST][
            ATTR_SMART_ATTRS
        ].get(self._attribute_id_str)

    def _update_state_and_attributes(self) -> None:
        """Update the sensor state and extra attributes from current attribute data."""
        current_attr_data = self._get_current_attribute_data()

        if not current_attr_data:  # If data for this attribute is not found
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return

        # The native_value of this sensor is the status of the SMART attribute.
        status_code = current_attr_data.get(ATTR_SMART_ATTRIBUTE_STATUS_CODE)
        self._attr_native_value = (
            ATTR_SMART_STATUS_MAP.get(status_code, ATTR_SMART_STATUS_UNKNOWN)
            if status_code is not None
            else ATTR_SMART_STATUS_UNKNOWN
        )

        # Populate extra state attributes with detailed
        #  information about the SMART attribute.
        attributes: dict[str, Any] = {
            ATTR_ATTRIBUTE_ID: current_attr_data.get(
                ATTR_ATTRIBUTE_ID
            ),  # Numeric ID (e.g., 5)
            "attribute_key_id": self._attribute_id_str,  # String ID (e.g., "5")
            ATTR_RAW_VALUE: current_attr_data.get(ATTR_RAW_VALUE),
            ATTR_RAW_STRING: current_attr_data.get(ATTR_RAW_STRING),
            ATTR_NORMALIZED_VALUE: current_attr_data.get(
                ATTR_NORMALIZED_VALUE
            ),  # "value" in API
            ATTR_WORST: current_attr_data.get(ATTR_WORST),
            ATTR_THRESH: current_attr_data.get(ATTR_THRESH),
            ATTR_WHEN_FAILED: current_attr_data.get(ATTR_WHEN_FAILED),
            ATTR_STATUS_REASON: current_attr_data.get(ATTR_STATUS_REASON),
            ATTR_FAILURE_RATE: current_attr_data.get(ATTR_FAILURE_RATE),
            # Add metadata attributes
            ATTR_DESCRIPTION: self._attribute_metadata.get(ATTR_DESCRIPTION),
            ATTR_IS_CRITICAL: self._attribute_metadata.get(ATTR_IS_CRITICAL),
            ATTR_IDEAL_VALUE_DIRECTION: self._attribute_metadata.get(
                ATTR_IDEAL_VALUE_DIRECTION
            ),
            "attribute_display_name": self._attribute_metadata.get(ATTR_DISPLAY_NAME),
        }
        # Filter out any attributes that are None to keep the state attributes clean.
        self._attr_extra_state_attributes = {
            k: v for k, v in attributes.items() if v is not None
        }

    def _handle_coordinator_update(self) -> None:
        """
        Handle updated data from the coordinator.

        Called by CoordinatorEntity when new data is available.
        """
        if not self.available:
            # If the sensor becomes unavailable
            #  (e.g., disk removed or attribute disappeared)
            if (
                self._attr_native_value is not None
            ):  # Check if it was previously available
                self._attr_native_value = None
                self._attr_extra_state_attributes = {}
                self.async_write_ha_state()  # Update HA state
            return

        # If available, update state and attributes and write to HA.
        self._update_state_and_attributes()
        self.async_write_ha_state()
