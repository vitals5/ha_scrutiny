"""Sensor platform for Scrutiny."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ScrutinyConfigEntry
from .const import (
    ATTR_CAPACITY,
    ATTR_DEVICE_NAME,
    ATTR_DEVICE_STATUS,
    ATTR_FIRMWARE,
    ATTR_MODEL_NAME,
    ATTR_POWER_ON_HOURS,
    ATTR_TEMPERATURE,
    DOMAIN,
    LOGGER,
    SCRUTINY_DEVICE_STATUS_MAP,
    SCRUTINY_DEVICE_STATUS_UNKNOWN,
)
from .coordinator import ScrutinyDataUpdateCoordinator

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_TEMPERATURE,
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=ATTR_POWER_ON_HOURS,
        name="Power On Hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:timer-sand",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key=ATTR_DEVICE_STATUS,
        name="Status",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.ENUM,
        options=[*SCRUTINY_DEVICE_STATUS_MAP.values(), SCRUTINY_DEVICE_STATUS_UNKNOWN],
    ),
    SensorEntityDescription(
        key=ATTR_CAPACITY,
        name="Capacity",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        icon="mdi:database",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScrutinyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Scrutiny sensor entities from a config entry."""
    coordinator = entry.runtime_data

    if not coordinator.data:
        LOGGER.info(
            "No disk data from Scrutiny coordinator; sensors will not be set up yet"
        )
        return

    entities_to_add: list[ScrutinyDiskSensor] = []
    for wwn, disk_full_data in coordinator.data.items():
        device_data = disk_full_data.get("device", {})

        device_info = DeviceInfo(
            identifiers={(DOMAIN, wwn)},
            name=(
                f"{device_data.get(ATTR_MODEL_NAME, 'Disk')} "
                f"({device_data.get(ATTR_DEVICE_NAME, wwn[-6:])})"
            ),
            model=device_data.get(ATTR_MODEL_NAME),
            manufacturer=device_data.get("manufacturer") or "Scrutiny Reported",
            sw_version=device_data.get(ATTR_FIRMWARE),
            via_device=(DOMAIN, entry.entry_id),
        )
        entities_to_add.extend(
            ScrutinyDiskSensor(
                coordinator=coordinator,
                entity_description=description,
                wwn=wwn,
                device_info=device_info,
            )
            for description in SENSOR_DESCRIPTIONS
        )

    if entities_to_add:
        async_add_entities(entities_to_add)


class ScrutinyDiskSensor(
    CoordinatorEntity[ScrutinyDataUpdateCoordinator], SensorEntity
):
    """Representation of a Scrutiny Disk Sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ScrutinyDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        wwn: str,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._wwn = wwn
        self._attr_device_info = device_info
        self._attr_unique_id = f"{DOMAIN}_{self._wwn}_{self.entity_description.key}"
        self._update_sensor_state()

    @property
    def available(self) -> bool:
        """Return True if coordinator has data and this sensor's disk is present."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._wwn in self.coordinator.data
        )

    def _update_sensor_state(self) -> None:
        """Update the state of the sensor from coordinator data."""
        if not self.available:
            return

        disk_data = self.coordinator.data[self._wwn]
        device_details = disk_data.get("device", {})
        smart_details = disk_data.get("smart", {})
        key = self.entity_description.key
        value = None

        if key == ATTR_TEMPERATURE:
            value = smart_details.get(ATTR_TEMPERATURE)
        elif key == ATTR_POWER_ON_HOURS:
            value = smart_details.get(ATTR_POWER_ON_HOURS)
        elif key == ATTR_DEVICE_STATUS:
            status_code = device_details.get(ATTR_DEVICE_STATUS)
            value = (
                SCRUTINY_DEVICE_STATUS_MAP.get(
                    status_code, SCRUTINY_DEVICE_STATUS_UNKNOWN
                )
                if status_code is not None
                else SCRUTINY_DEVICE_STATUS_UNKNOWN
            )
        elif key == ATTR_CAPACITY:
            capacity_bytes = device_details.get(ATTR_CAPACITY)
            if capacity_bytes is not None:
                value = round(capacity_bytes / (1024**3), 2)

        self._attr_native_value = value

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_sensor_state()
        self.async_write_ha_state()
