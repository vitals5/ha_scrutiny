"""Sensor platform for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

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

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import ScrutinyConfigEntry


MAIN_DISK_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_TEMPERATURE,
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_POWER_ON_HOURS,
        name="Power On Hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:timer-sand",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_SUMMARY_DEVICE_STATUS,
        name="Overall Device Status",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.ENUM,
        options=[
            *SCRUTINY_DEVICE_SUMMARY_STATUS_MAP.values(),
            SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN,
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=ATTR_CAPACITY,
        name="Capacity",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        icon="mdi:database",
        state_class=SensorStateClass.MEASUREMENT,
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
        key=ATTR_SMART_OVERALL_STATUS,
        name="SMART Test Result",
        icon="mdi:shield-check-outline",
        device_class=SensorDeviceClass.ENUM,
        options=[*ATTR_SMART_STATUS_MAP.values(), ATTR_SMART_STATUS_UNKNOWN],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ScrutinyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scrutiny sensor entities from a config entry."""
    coordinator: ScrutinyDataUpdateCoordinator = entry.runtime_data

    if not coordinator.data:
        LOGGER.info(
            "No disk data from Scrutiny coordinator for %s; "
            "sensor setup skipped for now.",
            entry.title,
        )
        return

    entities_to_add: list[SensorEntity] = []

    for wwn, aggregated_disk_data in coordinator.data.items():
        summary_device_data = aggregated_disk_data.get(KEY_SUMMARY_DEVICE, {})
        details_smart_latest = aggregated_disk_data.get(KEY_DETAILS_SMART_LATEST, {})
        details_metadata = aggregated_disk_data.get(KEY_DETAILS_METADATA, {})

        device_info_name = (
            f"{summary_device_data.get(ATTR_MODEL_NAME, 'Disk')} "
            f"({summary_device_data.get(ATTR_DEVICE_NAME, wwn[-6:])})"
        )
        device_info = DeviceInfo(
            identifiers={(DOMAIN, wwn)},
            name=device_info_name,
            model=summary_device_data.get(ATTR_MODEL_NAME),
            manufacturer=summary_device_data.get("manufacturer") or INTEGRATION_NAME,
            sw_version=summary_device_data.get(ATTR_FIRMWARE),
            via_device=(DOMAIN, entry.entry_id),
        )

        entities_to_add.extend(
            [
                ScrutinyMainDiskSensor(
                    coordinator=coordinator,
                    entity_description=description,
                    wwn=wwn,
                    device_info=device_info,
                )
                for description in MAIN_DISK_SENSOR_DESCRIPTIONS
            ]
        )

        smart_attributes_data = details_smart_latest.get(ATTR_SMART_ATTRS, {})
        if isinstance(smart_attributes_data, dict):
            for attr_id_str_key, attr_data_value in smart_attributes_data.items():
                if not isinstance(attr_data_value, dict):
                    LOGGER.warning(
                        "Skipping SMART attribute %s for disk %s:"
                        " unexpected data format %s",
                        attr_id_str_key,
                        wwn,
                        type(attr_data_value),
                    )
                    continue

                numeric_attr_id = attr_data_value.get(ATTR_ATTRIBUTE_ID)
                if numeric_attr_id is None:
                    LOGGER.warning(
                        "SMART attribute for disk %s (key %s)"
                        " is missing '%s'. Data: %s",
                        wwn,
                        attr_id_str_key,
                        ATTR_ATTRIBUTE_ID,
                        attr_data_value,
                    )
                    continue

                attr_metadata = details_metadata.get(str(numeric_attr_id), {})

                LOGGER.debug(
                    "ASYNC_SETUP_ENTRY (WWN: %s, AttrID_str: %s, NumID: %s): "
                    "Passing to SENSOR constructor-> attribute_metadata: %s (Type: %s)",
                    wwn,
                    attr_id_str_key,
                    numeric_attr_id,
                    str(attr_metadata)[:500],  # Logge einen Teil
                    type(attr_metadata),
                )

                entities_to_add.append(
                    ScrutinySmartAttributeSensor(
                        coordinator=coordinator,
                        wwn=wwn,
                        device_info=device_info,
                        attribute_id_str=attr_id_str_key,
                        attribute_metadata=attr_metadata,
                    )
                )
        else:
            LOGGER.warning(
                "SMART attributes data for disk %s is not a dict: %s",
                wwn,
                type(smart_attributes_data),
            )

    if entities_to_add:
        async_add_entities(entities_to_add)


class ScrutinyMainDiskSensor(
    CoordinatorEntity[ScrutinyDataUpdateCoordinator], SensorEntity
):
    """Representation of a main sensor for a Scrutiny-monitored disk."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: ScrutinyDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        wwn: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the main disk sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._wwn = wwn
        self._attr_device_info = device_info
        self._attr_unique_id = f"{DOMAIN}_{self._wwn}_{self.entity_description.key}"
        self._update_sensor_state()

    @property
    def available(self) -> bool:
        """Return True if sensor is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._wwn in self.coordinator.data
            and KEY_SUMMARY_DEVICE in self.coordinator.data[self._wwn]
        )

    def _update_sensor_state(self) -> None:
        """Update the sensor's state from coordinator data."""
        if not self.available:
            self._attr_native_value = None
            return

        data = self.coordinator.data[self._wwn]
        summary_device_data = data.get(KEY_SUMMARY_DEVICE, {})
        summary_smart_data = data.get(KEY_SUMMARY_SMART, {})
        details_smart_latest = data.get(KEY_DETAILS_SMART_LATEST, {})
        key = self.entity_description.key
        value = None

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
                value = round(capacity_bytes / (1024**3), 2)
        elif key == ATTR_POWER_CYCLE_COUNT:
            value = details_smart_latest.get(ATTR_POWER_CYCLE_COUNT)
        elif key == ATTR_SMART_OVERALL_STATUS:
            status_code = details_smart_latest.get(ATTR_SMART_OVERALL_STATUS)
            value = (
                ATTR_SMART_STATUS_MAP.get(status_code, ATTR_SMART_STATUS_UNKNOWN)
                if status_code is not None
                else ATTR_SMART_STATUS_UNKNOWN
            )
        self._attr_native_value = value

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_sensor_state()
        self.async_write_ha_state()


class ScrutinySmartAttributeSensor(
    CoordinatorEntity[ScrutinyDataUpdateCoordinator], SensorEntity
):
    """Representation of a single SMART attribute for a Scrutiny-monitored disk."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = False  # We set _attr_name directly

    def __init__(
        self,
        coordinator: ScrutinyDataUpdateCoordinator,
        wwn: str,
        device_info: DeviceInfo,
        attribute_id_str: str,
        attribute_metadata: dict[str, Any],
    ) -> None:
        """Initialize the SMART attribute sensor."""
        super().__init__(coordinator)
        self._wwn = wwn
        self._attribute_id_str = attribute_id_str
        self._attribute_metadata = attribute_metadata
        self._attr_device_info = device_info

        LOGGER.debug(
            "SMART ATTR INIT (WWN: %s, AttrID_str: %s): Full Metadata received: %s",
            wwn,
            attribute_id_str,
            attribute_metadata,
        )

        display_name_meta = self._attribute_metadata.get(ATTR_DISPLAY_NAME)

        LOGGER.debug(
            """SMART ATTR INIT (WWN: %s, AttrID_str: %s):
            Extracted display_name_meta: %s (Type: %s)""",
            wwn,
            attribute_id_str,
            display_name_meta,
            type(display_name_meta),
        )

        # Use the extracted display_name for the entity name suffix
        self.entity_name_suffix = (
            display_name_meta
            if display_name_meta
            else f"Attribute {self._attribute_id_str}"
        )

        self._attr_name = f"SMART {self._attribute_id_str}: {self.entity_name_suffix}"

        LOGGER.debug(
            "SMART ATTR INIT (WWN: %s, AttrID_str: %s): Final _attr_name: %s",
            wwn,
            attribute_id_str,
            self._attr_name,
        )

        slugified_name_part = slugify(
            self.entity_name_suffix
        )  # Slugify the suffix part
        unique_id_base = f"{DOMAIN}_{self._wwn}_smart_{self._attribute_id_str}"
        self._attr_unique_id = f"{unique_id_base}_{slugified_name_part}"

        LOGGER.debug(
            "SMART ATTR INIT (WWN: %s, AttrID_str: %s): Final unique_id: %s",
            wwn,
            attribute_id_str,
            self._attr_unique_id,
        )

        self.entity_description = SensorEntityDescription(
            key=f"smart_attr_{self._attribute_id_str}",
            # For consistency, not directly used for entity name
            name=self.entity_name_suffix,
            device_class=SensorDeviceClass.ENUM,
            options=[*ATTR_SMART_STATUS_MAP.values(), ATTR_SMART_STATUS_UNKNOWN],
        )

        self._update_state_and_attributes()

    @property
    def available(self) -> bool:
        """Return True if sensor is available."""
        if not (
            super().available
            and self.coordinator.data is not None
            and self._wwn in self.coordinator.data
        ):
            return False

        disk_agg_data = self.coordinator.data[self._wwn]
        latest_smart = disk_agg_data.get(KEY_DETAILS_SMART_LATEST)
        if not isinstance(latest_smart, dict):
            return False

        attrs = latest_smart.get(ATTR_SMART_ATTRS)
        if not isinstance(attrs, dict):
            return False

        return self._attribute_id_str in attrs

    def _get_current_attribute_data(self) -> dict[str, Any] | None:
        """Safely retrieve the current data for this specific SMART attribute."""
        if not self.available:
            return None
        # If available is true, this path should be safe.
        return self.coordinator.data[self._wwn][KEY_DETAILS_SMART_LATEST][
            ATTR_SMART_ATTRS
        ].get(self._attribute_id_str)

    def _update_state_and_attributes(self) -> None:
        """Update the sensor's state and attributes from current attribute data."""
        current_attr_data = self._get_current_attribute_data()

        if not current_attr_data:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return

        status_code = current_attr_data.get(ATTR_SMART_ATTRIBUTE_STATUS_CODE)
        self._attr_native_value = (
            ATTR_SMART_STATUS_MAP.get(status_code, ATTR_SMART_STATUS_UNKNOWN)
            if status_code is not None
            else ATTR_SMART_STATUS_UNKNOWN
        )

        attributes: dict[str, Any] = {
            ATTR_ATTRIBUTE_ID: current_attr_data.get(ATTR_ATTRIBUTE_ID),
            "attribute_key_id": self._attribute_id_str,
            ATTR_RAW_VALUE: current_attr_data.get(ATTR_RAW_VALUE),
            ATTR_RAW_STRING: current_attr_data.get(ATTR_RAW_STRING),
            ATTR_NORMALIZED_VALUE: current_attr_data.get(ATTR_NORMALIZED_VALUE),
            ATTR_WORST: current_attr_data.get(ATTR_WORST),
            ATTR_THRESH: current_attr_data.get(ATTR_THRESH),
            ATTR_WHEN_FAILED: current_attr_data.get(ATTR_WHEN_FAILED),
            ATTR_STATUS_REASON: current_attr_data.get(ATTR_STATUS_REASON),
            ATTR_FAILURE_RATE: current_attr_data.get(ATTR_FAILURE_RATE),
            ATTR_DESCRIPTION: self._attribute_metadata.get(ATTR_DESCRIPTION),
            ATTR_IS_CRITICAL: self._attribute_metadata.get(ATTR_IS_CRITICAL),
            ATTR_IDEAL_VALUE_DIRECTION: self._attribute_metadata.get(
                ATTR_IDEAL_VALUE_DIRECTION
            ),
            "attribute_display_name": self._attribute_metadata.get(ATTR_DISPLAY_NAME),
        }
        self._attr_extra_state_attributes = {
            k: v for k, v in attributes.items() if v is not None
        }

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.available:
            if self._attr_native_value is not None:
                self._attr_native_value = None
                self._attr_extra_state_attributes = {}
                self.async_write_ha_state()
            return

        self._update_state_and_attributes()
        self.async_write_ha_state()
