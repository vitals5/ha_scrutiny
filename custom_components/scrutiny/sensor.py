"""Sensor platform for the Scrutiny Home Assistant integration."""

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from . import ScrutinyConfigEntry
from .const import (
    ATTR_ARCHIVED,
    ATTR_ATTRIBUTE_ID,
    ATTR_CAPACITY,
    ATTR_DESCRIPTION,
    ATTR_DEVICE_NAME,
    ATTR_DISPLAY_NAME,
    ATTR_FIRMWARE,
    ATTR_IDEAL_VALUE_DIRECTION,
    ATTR_IS_CRITICAL,
    ATTR_MODEL_NAME,
    ATTR_NORMALIZED_VALUE,
    ATTR_POWER_CYCLE_COUNT,
    ATTR_POWER_ON_HOURS,
    ATTR_RAW_STRING,
    ATTR_RAW_VALUE,
    ATTR_SERIAL_NUMBER,
    ATTR_SMART_ATTRIBUTE_STATUS_CODE,
    ATTR_SMART_ATTRS,
    ATTR_SMART_OVERALL_STATUS,
    ATTR_SMART_STATUS_MAP,
    ATTR_SMART_STATUS_UNKNOWN,
    ATTR_SUMMARY_DEVICE_STATUS,
    ATTR_TEMPERATURE,
    ATTR_THRESH,
    ATTR_UPDATED_AT,
    ATTR_WHEN_FAILED,
    ATTR_WORST,
    CONF_ENABLE_ALL_ATTRS,
    CONF_ENABLE_CRITICAL_ATTRS,
    CONF_ENABLE_RAW_VALUES,
    CONF_URL,
    DEFAULT_ENABLE_ALL_ATTRS,
    DEFAULT_ENABLE_CRITICAL_ATTRS,
    DEFAULT_ENABLE_RAW_VALUES,
    DOMAIN,
    KEY_DETAILS_METADATA,
    KEY_DETAILS_SMART_LATEST,
    KEY_SUMMARY_DEVICE,
    KEY_SUMMARY_SMART,
    LOGGER,
    SCRUTINY_DEVICE_SUMMARY_STATUS_MAP,
    SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN,
)
from .const import (
    NAME as INTEGRATION_NAME,
)
from .coordinator import ScrutinyDataUpdateCoordinator

# Coordinator-based entities push updates themselves; no parallel fetching needed.
PARALLEL_UPDATES = 0


# One SensorEntityDescription per metric exposed for every monitored disk.
MAIN_DISK_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_TEMPERATURE,
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_POWER_ON_HOURS,
        translation_key="power_on_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_SUMMARY_DEVICE_STATUS,
        translation_key="overall_device_status",
        device_class=SensorDeviceClass.ENUM,
        options=[
            *SCRUTINY_DEVICE_SUMMARY_STATUS_MAP.values(),
            SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN,
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_CAPACITY,
        translation_key="capacity",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_POWER_CYCLE_COUNT,
        translation_key="power_cycle_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_SMART_OVERALL_STATUS,
        translation_key="smart_test_result",
        device_class=SensorDeviceClass.ENUM,
        options=[*ATTR_SMART_STATUS_MAP.values(), ATTR_SMART_STATUS_UNKNOWN],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_UPDATED_AT,
        translation_key="last_smart_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - hass is not directly used but required by the signature
    entry: ScrutinyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scrutiny sensor entities from a config entry."""
    # Retrieve the coordinator instance stored in the config entry's runtime_data.
    coordinator: ScrutinyDataUpdateCoordinator = entry.runtime_data

    # Skip setup when no disk data is available yet.
    if not coordinator.data:
        LOGGER.info(
            "No disk data from Scrutiny coordinator for %s; "
            "sensor setup skipped for now.",
            entry.title,
        )
        return

    # Read entity-level options — controls which SMART attribute sensors are created.
    enable_critical_attrs: bool = entry.options.get(
        CONF_ENABLE_CRITICAL_ATTRS, DEFAULT_ENABLE_CRITICAL_ATTRS
    )
    enable_all_attrs: bool = entry.options.get(
        CONF_ENABLE_ALL_ATTRS, DEFAULT_ENABLE_ALL_ATTRS
    )
    enable_raw_values: bool = entry.options.get(
        CONF_ENABLE_RAW_VALUES, DEFAULT_ENABLE_RAW_VALUES
    )

    entities_to_add: list[SensorEntity] = []

    # Iterate over each disk returned by the coordinator.
    for disk_id, aggregated_disk_data in coordinator.data.items():
        summary_device_data = aggregated_disk_data.get(KEY_SUMMARY_DEVICE, {})
        details_smart_latest = aggregated_disk_data.get(KEY_DETAILS_SMART_LATEST, {})
        details_metadata = aggregated_disk_data.get(KEY_DETAILS_METADATA, {})

        is_archived = summary_device_data.get(ATTR_ARCHIVED, False)

        # Build the device name. Archived disks are labelled clearly so they
        # remain identifiable in the HA device list.
        serial_number = summary_device_data.get(ATTR_SERIAL_NUMBER)
        model_part = summary_device_data.get(ATTR_MODEL_NAME, "Disk")
        id_part = serial_number or disk_id[-6:]
        device_info_name = f"{model_part} ({id_part})"
        if is_archived:
            device_info_name = f"{device_info_name} [Archived]"

        _base_url = entry.data.get(CONF_URL, "").rstrip("/")
        device_info = DeviceInfo(
            identifiers={(DOMAIN, disk_id)},
            name=device_info_name,
            model=summary_device_data.get(ATTR_MODEL_NAME),
            serial_number=serial_number,
            manufacturer=summary_device_data.get("manufacturer") or INTEGRATION_NAME,
            sw_version=summary_device_data.get(ATTR_FIRMWARE),
            configuration_url=(
                f"{_base_url}/web/device/{disk_id}" if _base_url else None
            ),
            via_device=(
                DOMAIN,
                entry.entry_id,
            ),
        )

        # Create the main disk sensors (Temperature, Power On Hours, etc.) for this disk
        entities_to_add.extend(
            [
                ScrutinyMainDiskSensor(
                    coordinator=coordinator,
                    entity_description=description,
                    disk_id=disk_id,
                    device_info=device_info,
                    serial_number=serial_number,
                    is_archived=is_archived,
                )
                for description in MAIN_DISK_SENSOR_DESCRIPTIONS
            ]
        )

        # Create sensors for individual SMART attributes of this disk.
        # Only create them if the user has opted in via options — creating sensors
        # that are just immediately disabled wastes resources and clutters the UI.
        if enable_critical_attrs or enable_all_attrs:
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
                            disk_id,
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
                            disk_id,
                            attr_id_str_key,
                            ATTR_ATTRIBUTE_ID,
                            attr_data_value,
                        )
                        continue

                    actual_attribute_id_for_sensor = str(numeric_attr_id)
                    attr_metadata = details_metadata.get(
                        actual_attribute_id_for_sensor, {}
                    )
                    is_critical = bool(attr_metadata.get(ATTR_IS_CRITICAL, False))

                    # Skip non-critical attributes unless the user wants all of them.
                    if not enable_all_attrs and not is_critical:
                        continue

                    entities_to_add.append(
                        ScrutinySmartAttributeSensor(
                            coordinator=coordinator,
                            disk_id=disk_id,
                            device_info=device_info,
                            attribute_id_str=actual_attribute_id_for_sensor,
                            attribute_metadata=attr_metadata,
                            serial_number=serial_number,
                            is_archived=is_archived,
                        )
                    )

                    # Optionally create a companion numeric sensor for the raw
                    # value so HA can record its history and long-term statistics.
                    # Only created when the user has opted in AND the attribute
                    # itself is already being tracked (critical/all filter above).
                    if enable_raw_values:
                        entities_to_add.append(
                            ScrutinySmartRawValueSensor(
                                coordinator=coordinator,
                                disk_id=disk_id,
                                device_info=device_info,
                                attribute_id_str=actual_attribute_id_for_sensor,
                                attribute_metadata=attr_metadata,
                                serial_number=serial_number,
                                is_archived=is_archived,
                            )
                        )
            else:
                LOGGER.warning(
                    (
                        "SMART attributes data for disk %s is not a dict: "
                        "%s. Skipping SMART attribute sensors."
                    ),
                    disk_id,
                    type(smart_attributes_data),
                )

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
        entity_description: SensorEntityDescription,
        disk_id: str,
        device_info: DeviceInfo,
        serial_number: str | None = None,
        is_archived: bool = False,
    ) -> None:
        """Initialize the main disk sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._disk_id = disk_id
        self._serial_number = serial_number
        self._is_archived = is_archived
        self._attr_device_info = device_info
        self._attr_unique_id = f"{DOMAIN}_{self._disk_id}_{self.entity_description.key}"
        self._update_sensor_state()

    @property
    def available(self) -> bool:
        """Return True if the sensor's data is available from the coordinator."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._disk_id in self.coordinator.data
            and KEY_SUMMARY_DEVICE in self.coordinator.data[self._disk_id]
        )

    def _update_sensor_state(self) -> None:
        """Update the sensor's state (native_value) from coordinator data."""
        if not self.available:
            self._attr_native_value = None
            return

        data = self.coordinator.data[self._disk_id]
        summary_device_data = data.get(KEY_SUMMARY_DEVICE, {})
        summary_smart_data = data.get(KEY_SUMMARY_SMART, {})
        details_smart_latest = data.get(KEY_DETAILS_SMART_LATEST, {})

        key = self.entity_description.key
        value = None

        # Values prefer the detailed snapshot; summary is the fallback.
        if key == ATTR_TEMPERATURE:
            value = details_smart_latest.get(
                ATTR_TEMPERATURE, summary_smart_data.get(ATTR_TEMPERATURE)
            )
        elif key == ATTR_POWER_ON_HOURS:
            # Scrutiny returns power-on time as an integer number of hours.
            # Store the raw hours value; HA converts to days for display via
            # suggested_unit_of_measurement without any lossy round-trip.
            value = details_smart_latest.get(
                ATTR_POWER_ON_HOURS, summary_smart_data.get(ATTR_POWER_ON_HOURS)
            )
        elif key == ATTR_SUMMARY_DEVICE_STATUS:
            status_code = summary_device_data.get(ATTR_SUMMARY_DEVICE_STATUS)
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
        elif key == ATTR_UPDATED_AT:
            # Parse Scrutiny's ISO 8601 timestamp to an aware datetime.
            # Scrutiny uses Go's time format which includes nanoseconds, e.g.
            # "2025-08-06T07:00:13.499643907Z". Python's fromisoformat handles
            # this correctly on 3.11+; truncate to microseconds for safety.
            raw_ts = summary_device_data.get(ATTR_UPDATED_AT)
            if raw_ts is not None:
                try:
                    # Truncate sub-microsecond precision then parse.
                    ts_str = str(raw_ts)
                    if "." in ts_str:
                        dot_pos = ts_str.index(".")
                        suffix = ts_str[dot_pos:]
                        # Keep at most 6 decimal digits before any trailing 'Z'/offset
                        tz_pos = next(
                            (
                                i
                                for i, c in enumerate(suffix)
                                if c in ("Z", "+", "-") and i > 0
                            ),
                            len(suffix),
                        )
                        frac = suffix[1:tz_pos][:6]
                        tz_part = suffix[tz_pos:]
                        ts_str = ts_str[:dot_pos] + "." + frac + tz_part
                    # Replace trailing Z with +00:00 for fromisoformat
                    ts_str = ts_str.replace("Z", "+00:00")
                    value = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):  # fmt: skip
                    LOGGER.debug(
                        "Could not parse UpdatedAt timestamp for %s: %r",
                        self._disk_id,
                        raw_ts,
                    )
                    value = None
        self._attr_native_value = value

        # Expose serial number, device path, and archived status as extra attributes.
        extra: dict[str, Any] = {}
        if self._serial_number:
            extra[ATTR_SERIAL_NUMBER] = self._serial_number
        device_path = summary_device_data.get(ATTR_DEVICE_NAME)
        if device_path:
            extra[ATTR_DEVICE_NAME] = device_path
        if self._is_archived:
            extra[ATTR_ARCHIVED] = True
        self._attr_extra_state_attributes = extra or {}

    def _handle_coordinator_update(self) -> None:
        """
        Handle updated data from the coordinator.
        This method is called by CoordinatorEntity
        when the coordinator signals new data.
        """  # noqa: D205
        self._update_sensor_state()
        self.async_write_ha_state()


class ScrutinySmartAttributeSensor(
    CoordinatorEntity[ScrutinyDataUpdateCoordinator], SensorEntity
):
    """Representation of a single SMART attribute for a Scrutiny-monitored disk."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ScrutinyDataUpdateCoordinator,
        disk_id: str,
        device_info: DeviceInfo,
        # String representation of the SMART attribute ID (e.g., "5", "194")
        attribute_id_str: str,
        attribute_metadata: dict[str, Any],
        serial_number: str | None = None,
        is_archived: bool = False,
    ) -> None:
        """Initialize the SMART attribute sensor."""
        super().__init__(coordinator)
        self._disk_id = disk_id
        self._serial_number = serial_number
        self._is_archived = is_archived
        self._attribute_id_str = attribute_id_str
        self._attribute_metadata = (
            attribute_metadata  # e.g., {"display_name": "Reallocated Sector Ct", ...}
        )
        self._attr_device_info = device_info

        # Get the display name from metadata, e.g., "Reallocated Sectors Count".
        display_name_meta = self._attribute_metadata.get(ATTR_DISPLAY_NAME)

        if display_name_meta:
            self.attribute_name_for_entity_description = display_name_meta
        elif not self._attribute_id_str.isdecimal():  # e.g. "critical_warning"
            self.attribute_name_for_entity_description = self._attribute_id_str.replace(
                "_", " "
            ).title()
        else:  # e.g. "5"
            self.attribute_name_for_entity_description = (
                f"Attribute {self._attribute_id_str}"
            )

        # Define the entity description for this SMART attribute sensor.
        # The state of this sensor will be the status
        #  of the SMART attribute (e.g., "Passed", "Failed").
        self.entity_description = SensorEntityDescription(
            key=f"smart_attr_{slugify(self._attribute_id_str)}",
            name=self.attribute_name_for_entity_description,
            translation_key="smart_attribute",
            device_class=SensorDeviceClass.ENUM,
            options=[*ATTR_SMART_STATUS_MAP.values(), ATTR_SMART_STATUS_UNKNOWN],
        )

        slugified_display_name_for_id = slugify(
            self.attribute_name_for_entity_description
        )
        self._attr_unique_id = (
            f"{DOMAIN}_{self._disk_id}_smart_"
            f"{slugify(self._attribute_id_str)}_{slugified_display_name_for_id}"
        )

        self._update_state_and_attributes()

    @property
    def available(self) -> bool:
        """Return True if the sensor's data is available from the coordinator."""
        if not (
            super().available
            and self.coordinator.data is not None
            and self._disk_id in self.coordinator.data
        ):
            return False

        # Check if the detailed SMART data and specific attribute exist.
        disk_agg_data = self.coordinator.data[self._disk_id]
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
        return self.coordinator.data[self._disk_id][KEY_DETAILS_SMART_LATEST][
            ATTR_SMART_ATTRS
        ].get(self._attribute_id_str)

    def _update_state_and_attributes(self) -> None:
        """Update the sensor state and extra attributes from current attribute data."""
        current_attr_data = self._get_current_attribute_data()

        if not current_attr_data:
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

        summary_device_data = self.coordinator.data.get(self._disk_id, {}).get(
            KEY_SUMMARY_DEVICE, {}
        )
        # when_failed is typically "-" (meaning never failed); only include it when
        # it carries real information (i.e. the attribute has actually failed).
        when_failed = current_attr_data.get(ATTR_WHEN_FAILED)
        if when_failed == "-":
            when_failed = None

        attributes: dict[str, Any] = {
            ATTR_ATTRIBUTE_ID: current_attr_data.get(ATTR_ATTRIBUTE_ID),
            ATTR_RAW_VALUE: current_attr_data.get(ATTR_RAW_VALUE),
            ATTR_RAW_STRING: current_attr_data.get(ATTR_RAW_STRING),
            ATTR_NORMALIZED_VALUE: current_attr_data.get(ATTR_NORMALIZED_VALUE),
            ATTR_WORST: current_attr_data.get(ATTR_WORST),
            ATTR_THRESH: current_attr_data.get(ATTR_THRESH),
            ATTR_WHEN_FAILED: when_failed,
            ATTR_DESCRIPTION: self._attribute_metadata.get(ATTR_DESCRIPTION),
            ATTR_IS_CRITICAL: self._attribute_metadata.get(ATTR_IS_CRITICAL),
            ATTR_IDEAL_VALUE_DIRECTION: self._attribute_metadata.get(
                ATTR_IDEAL_VALUE_DIRECTION
            ),
            ATTR_SERIAL_NUMBER: self._serial_number,
            ATTR_DEVICE_NAME: summary_device_data.get(ATTR_DEVICE_NAME),
            ATTR_ARCHIVED: True if self._is_archived else None,
        }
        self._attr_extra_state_attributes = {
            k: v for k, v in attributes.items() if v is not None
        }

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Avoid a redundant HA state write when the sensor was already unavailable
        # and remains so — nothing changed from HA's perspective.
        was_unavailable = self._attr_native_value is None
        self._update_state_and_attributes()
        if was_unavailable and self._attr_native_value is None:
            return
        self.async_write_ha_state()


class ScrutinySmartRawValueSensor(
    CoordinatorEntity[ScrutinyDataUpdateCoordinator], SensorEntity
):
    """Numeric sensor exposing the raw value of a single SMART attribute.

    Unlike ``ScrutinySmartAttributeSensor`` (which reports pass/fail status),
    this sensor reports the raw integer value so Home Assistant can record its
    history and long-term statistics — making slow degradation trends visible
    over time (e.g. a gradually climbing Reallocated Sectors Count).
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ScrutinyDataUpdateCoordinator,
        disk_id: str,
        device_info: DeviceInfo,
        attribute_id_str: str,
        attribute_metadata: dict[str, Any],
        serial_number: str | None = None,
        is_archived: bool = False,
    ) -> None:
        """Initialize the raw value sensor."""
        super().__init__(coordinator)
        self._disk_id = disk_id
        self._serial_number = serial_number
        self._is_archived = is_archived
        self._attribute_id_str = attribute_id_str
        self._attribute_metadata = attribute_metadata
        self._attr_device_info = device_info

        display_name = attribute_metadata.get(ATTR_DISPLAY_NAME)
        if display_name:
            attr_label = display_name
        elif not attribute_id_str.isdecimal():
            attr_label = attribute_id_str.replace("_", " ").title()
        else:
            attr_label = f"Attribute {attribute_id_str}"

        self.entity_description = SensorEntityDescription(
            key=f"smart_raw_{slugify(attribute_id_str)}",
            name=f"{attr_label} (Raw)",
        )
        self._attr_icon = "mdi:counter"

        self._attr_unique_id = (
            f"{DOMAIN}_{self._disk_id}_smart_raw_"
            f"{slugify(attribute_id_str)}_{slugify(attr_label)}"
        )
        self._update_state()

    @property
    def available(self) -> bool:
        """Return True if the attribute data is present in the coordinator."""
        if not (
            super().available
            and self.coordinator.data is not None
            and self._disk_id in self.coordinator.data
        ):
            return False
        disk_data = self.coordinator.data[self._disk_id]
        latest = disk_data.get(KEY_DETAILS_SMART_LATEST)
        if not isinstance(latest, dict):
            return False
        attrs = latest.get(ATTR_SMART_ATTRS)
        if not isinstance(attrs, dict):
            return False
        return self._attribute_id_str in attrs

    def _update_state(self) -> None:
        """Update native_value from the current raw value in coordinator data."""
        if not self.available:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return

        attr_data = self.coordinator.data[self._disk_id][KEY_DETAILS_SMART_LATEST][
            ATTR_SMART_ATTRS
        ].get(self._attribute_id_str, {})

        raw = attr_data.get(ATTR_RAW_VALUE)
        # Raw values from Scrutiny are typically integers; coerce for safety.
        try:
            self._attr_native_value = int(raw) if raw is not None else None
        except (TypeError, ValueError):  # fmt: skip
            self._attr_native_value = None

        extra: dict[str, Any] = {
            ATTR_RAW_STRING: attr_data.get(ATTR_RAW_STRING),
        }
        if self._serial_number:
            extra[ATTR_SERIAL_NUMBER] = self._serial_number
        if self._is_archived:
            extra[ATTR_ARCHIVED] = True
        self._attr_extra_state_attributes = {
            k: v for k, v in extra.items() if v is not None
        }

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        was_unavailable = self._attr_native_value is None
        self._update_state()
        if was_unavailable and self._attr_native_value is None:
            return
        self.async_write_ha_state()
