"""Sensor platform for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING  # For an empty TYPE_CHECKING block if needed

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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

# Import the specific ConfigEntry type alias and Coordinator type
from .const import (
    ATTR_CAPACITY,
    ATTR_DEVICE,
    ATTR_DEVICE_NAME,
    ATTR_DEVICE_STATUS,
    ATTR_FIRMWARE,
    ATTR_MODEL_NAME,
    ATTR_POWER_ON_HOURS,
    ATTR_SMART,
    ATTR_TEMPERATURE,
    DOMAIN,
    LOGGER,
    SCRUTINY_DEVICE_STATUS_MAP,
    SCRUTINY_DEVICE_STATUS_UNKNOWN,
)
from .coordinator import ScrutinyDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import ScrutinyConfigEntry


# A tuple of SensorEntityDescription objects. Each description defines the static
# properties of a sensor type that will be created for each disk.
SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=ATTR_TEMPERATURE,  # Used to fetch the correct data from the coordinator
        name="Temperature",  # Default name suffix for the entity
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,  # Helps HA frontend display it
        state_class=SensorStateClass.MEASUREMENT,  # Indicates the sensor meas a value
    ),
    SensorEntityDescription(
        key=ATTR_POWER_ON_HOURS,
        name="Power On Hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:timer-sand",  # Material Design Icon for this sensor
        state_class=SensorStateClass.TOTAL_INCREASING,  # Value accumulates over time
    ),
    SensorEntityDescription(
        key=ATTR_DEVICE_STATUS,
        name="Status",
        icon="mdi:harddisk",
        # Sensor has a defined set of possible string states
        device_class=SensorDeviceClass.ENUM,
        # 'options' provides the list of possible states for ENUM device class.
        options=[*SCRUTINY_DEVICE_STATUS_MAP.values(), SCRUTINY_DEVICE_STATUS_UNKNOWN],
    ),
    SensorEntityDescription(
        key=ATTR_CAPACITY,
        name="Capacity",
        # Value will be converted to GB
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        icon="mdi:database",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,  # How many decimal places to show in UI
    ),
)


async def async_setup_entry(
    # The HomeAssistant instance (marked as unused by Ruff if
    # not directly used, but required by signature)
    hass: HomeAssistant,  # noqa: ARG001
    entry: ScrutinyConfigEntry,  # The config entry for this Scrutiny instance
    async_add_entities: AddEntitiesCallback,  # Callback to add entities to HA
) -> None:
    """
    Set up Scrutiny sensor entities from a config entry.

    This function is called by Home Assistant (forwarded from __init__.py)
    when the sensor platform for this integration's config entry is being set up.
    It discovers disks from the coordinator's data and creates sensor entities for them.
    """
    # Retrieve the data update coordinator instance stored in the config entry.
    coordinator: ScrutinyDataUpdateCoordinator = entry.runtime_data

    # If the coordinator has no data (e.g., API error on first fetch, or no disks),
    # log it and don't create any sensors yet.
    # The sensors will be created if/when data becomes available via coordinator updates
    # although this basic setup adds entities only once. For fully dynamic addition
    # of new disks appearing later, a more complex listener pattern would be needed.
    if not coordinator.data:
        LOGGER.info(
            "No disk data currently available from Scrutiny for %s; "
            "sensor setup will be skipped for now.",
            entry.title,
        )
        return  # Exit if no data to prevent errors

    entities_to_add: list[ScrutinyDiskSensor] = []

    # Iterate over each disk found in the coordinator's data.
    # The key 'wwn' is the World Wide Name of the disk, used as a unique identifier.
    # 'disk_full_data' contains 'device' and 'smart' sub-dictionaries from the API.
    for wwn, disk_full_data in coordinator.data.items():
        device_api_data = disk_full_data.get(
            ATTR_DEVICE, {}
        )  # Get the 'device' part of API data

        # Create a DeviceInfo object for each physical disk.
        # This groups all sensors for a single disk under
        # one "device" in Home Assistant's
        # device registry, providing a better user experience.
        device_info = DeviceInfo(
            identifiers={
                (DOMAIN, wwn)
            },  # Unique identifier for this device within this domain
            name=(
                # e.g., "MyDiskModel (sda)"
                f"{device_api_data.get(ATTR_MODEL_NAME, 'Disk')} "
                # Fallback to last 6 chars of WWN
                f"({device_api_data.get(ATTR_DEVICE_NAME, wwn[-6:])})"
            ),
            model=device_api_data.get(ATTR_MODEL_NAME),
            manufacturer=device_api_data.get("manufacturer")
            or "Scrutiny Reported",  # API might not provide manufacturer
            sw_version=device_api_data.get(ATTR_FIRMWARE),
            # hw_version could be ATTR_SERIAL_NUMBER if desired
            via_device=(
                DOMAIN,
                entry.entry_id,
            ),  # Links this disk device to the main integration "device"
        )

        # For each defined sensor type, create a sensor instance for the current disk.
        # Using list comprehension and extend for performance (Ruff PERF401).
        entities_to_add.extend(
            ScrutinyDiskSensor(
                coordinator=coordinator,
                entity_description=description,
                wwn=wwn,  # Pass the disk's WWN to the sensor
                device_info=device_info,  # Link sensor to its HA device
            )
            for description in SENSOR_DESCRIPTIONS
        )

    # Add all created sensor entities to Home Assistant if any were generated.
    if entities_to_add:
        async_add_entities(entities_to_add)


class ScrutinyDiskSensor(
    CoordinatorEntity[ScrutinyDataUpdateCoordinator], SensorEntity
):
    """
    Represents a single sensor for a specific Scrutiny-monitored disk.

    This class inherits from CoordinatorEntity to automatically update when the
    coordinator signals new data, and from SensorEntity to be a sensor.
    """

    # The _attr_has_entity_name attribute allows the entity's friendly name to be
    # partly derived from the device name and partly
    # from the SensorEntityDescription's name.
    # e.g., "MyDiskModel (sda) Temperature"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ScrutinyDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        wwn: str,  # The World Wide Name of the disk this sensor monitors
        device_info: DeviceInfo,  # DeviceInfo linking this sensor to its HA device
    ) -> None:
        """Initialize the disk sensor."""
        # Call the superclass __init__ for CoordinatorEntity, passing the coordinator.
        super().__init__(coordinator)
        # Store the SensorEntityDescription, which contains
        # static properties like name, key, unit.
        self.entity_description = entity_description
        # Store the WWN of the disk this sensor instance is for.
        self._wwn = wwn

        # Set device-specific attributes for Home Assistant.
        self._attr_device_info = device_info
        # Construct a unique ID for this entity within Home Assistant.
        # Format: <domain>_<disk_wwn>_<sensor_key>
        self._attr_unique_id = f"{DOMAIN}_{self._wwn}_{self.entity_description.key}"

        # Update the sensor's state based on the initial data from the coordinator.
        # This ensures the sensor has a value as
        # soon as it's created, if data is available.
        self._update_sensor_state()

    @property
    def available(self) -> bool:
        """
        Return True if the sensor is available.

        A sensor is available if:
        1. The CoordinatorEntity itself is available (i.e.,
        the coordinator is running and has recent data).
        2. The coordinator's data is not None.
        3. The data for this specific disk (identified by _wwn) exists
        in the coordinator's data.
        """
        return (
            super().available
            and self.coordinator.data is not None
            and self._wwn in self.coordinator.data
        )

    def _update_sensor_state(self) -> None:
        """
        Update the sensor's native_value based on the latest coordinator data.

        This method is called during initialization and by _handle_coordinator_update.
        """
        # If the sensor is not available (e.g., disk data missing), do nothing further.
        # The 'available' property and CoordinatorEntity will handle HA state.
        if not self.available:
            return  # self._attr_native_value will remain as is, or None if never set.

        # Retrieve the data for this specific disk from the coordinator.
        # We know self._wwn is in self.coordinator.data due to the `available` check.
        disk_data = self.coordinator.data[self._wwn]

        device_details = disk_data.get(
            ATTR_DEVICE, {}
        )  # Default to empty dict if 'device' key is missing
        smart_details = disk_data.get(
            ATTR_SMART, {}
        )  # Default to empty dict if 'smart' key is missing

        key = (
            self.entity_description.key
        )  # The key for this sensor type (e.g., ATTR_TEMPERATURE)
        value = None  # Default value if data extraction fails

        # Extract the appropriate value based on the sensor's key.
        if key == ATTR_TEMPERATURE:
            value = smart_details.get(ATTR_TEMPERATURE)
        elif key == ATTR_POWER_ON_HOURS:
            value = smart_details.get(ATTR_POWER_ON_HOURS)
        elif key == ATTR_DEVICE_STATUS:
            status_code = device_details.get(ATTR_DEVICE_STATUS)
            # Map the status code to a human-readable string.
            # If status_code is None or not in the map, use UNKNOWN.
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
                # Convert bytes to Gibibytes (GiB) for display.
                # 1 GiB = 1024^3 bytes.
                value = round(capacity_bytes / (1024**3), 2)

        # Set the sensor's native value.
        self._attr_native_value = value

    def _handle_coordinator_update(self) -> None:
        """
        Handle data updates from the coordinator.

        This method is called by the CoordinatorEntity base class whenever the
        coordinator successfully fetches new data.
        """
        # Re-calculate the sensor's state based on the new data.
        self._update_sensor_state()
        # Tell Home Assistant that the sensor's state may have
        # changed and it needs to be re-rendered.
        self.async_write_ha_state()
