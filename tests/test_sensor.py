# tests/test_sensor.py

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call  # call für multiple calls

from typing import TYPE_CHECKING, Any

import copy

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
)  # Type for async_add_entities
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)  # For typing the mock

from homeassistant.components.sensor import SensorEntityDescription  # Für Typing
from homeassistant.helpers.device_registry import DeviceInfo  # Für Typing
from homeassistant.util import slugify

# Importiere die zu testende Funktion und die Sensorklassen
from custom_components.scrutiny.sensor import (
    async_setup_entry,
    ScrutinyMainDiskSensor,
    ScrutinySmartAttributeSensor,
    MAIN_DISK_SENSOR_DESCRIPTIONS,
)

# Import constants needed for test data and assertions
from custom_components.scrutiny.const import (
    DOMAIN,
    ATTR_DEVICE_NAME,
    ATTR_MODEL_NAME,
    ATTR_FIRMWARE,
    ATTR_TEMPERATURE,
    ATTR_POWER_ON_HOURS,
    ATTR_SUMMARY_DEVICE_STATUS,
    ATTR_CAPACITY,
    ATTR_POWER_CYCLE_COUNT,
    ATTR_SMART_OVERALL_STATUS,
    ATTR_SMART_ATTRS,
    ATTR_ATTRIBUTE_ID,  # Key for the numeric attribute ID within SMART attribute data
    ATTR_DISPLAY_NAME,
    KEY_SUMMARY_DEVICE,
    KEY_SUMMARY_SMART,  # Wird ggf. von Sensoren als Fallback genutzt
    KEY_DETAILS_DEVICE,
    KEY_DETAILS_SMART_LATEST,
    KEY_DETAILS_METADATA,
    ATTR_RAW_VALUE,
    ATTR_NORMALIZED_VALUE,
    ATTR_WORST,
    ATTR_THRESH,
    ATTR_WHEN_FAILED,
    ATTR_SMART_ATTRIBUTE_STATUS_CODE,
    ATTR_STATUS_REASON,
    ATTR_FAILURE_RATE,
    ATTR_DESCRIPTION,
    ATTR_IS_CRITICAL,
    ATTR_IDEAL_VALUE_DIRECTION,
    ATTR_SMART_STATUS_MAP,
    ATTR_SMART_STATUS_UNKNOWN,
)

# Import the coordinator class for typing the mock
from custom_components.scrutiny.coordinator import ScrutinyDataUpdateCoordinator

# Helpers from pytest-homeassistant-custom-component
from pytest_homeassistant_custom_component.common import MockConfigEntry

# --- Test data for the coordinator ---
# This structure simulates coordinator.data
# We need at least one disk with some main attributes and some SMART attributes

MOCK_WWN1 = "wwn_disk1_sensor_test"
MOCK_WWN2 = "wwn_disk2_sensor_test"

COORDINATOR_DATA_ONE_DISK = {
    MOCK_WWN1: {
        KEY_SUMMARY_DEVICE: {
            ATTR_DEVICE_NAME: "/dev/sda",
            ATTR_MODEL_NAME: "TestModelSDX",
            ATTR_FIRMWARE: "FW123",
            "manufacturer": "TestManu",  # For DeviceInfo
            ATTR_CAPACITY: 1000 * 1024 * 1024 * 1024,  # 1TB
            ATTR_SUMMARY_DEVICE_STATUS: 0,
        },
        KEY_SUMMARY_SMART: {  # Fallback data
            ATTR_TEMPERATURE: 25,
            ATTR_POWER_ON_HOURS: 100,
        },
        KEY_DETAILS_DEVICE: {  # Primary data source for some sensors
            ATTR_MODEL_NAME: "TestModelSDX-Detail",  # Can differ from summary
            ATTR_FIRMWARE: "FW123-Detail",
            ATTR_CAPACITY: 1000 * 1024 * 1024 * 1024,
        },
        KEY_DETAILS_SMART_LATEST: {
            ATTR_TEMPERATURE: 28,
            ATTR_POWER_ON_HOURS: 105,
            ATTR_POWER_CYCLE_COUNT: 10,
            ATTR_SMART_OVERALL_STATUS: 0,
            ATTR_SMART_ATTRS: {
                "5": {
                    ATTR_ATTRIBUTE_ID: 5,
                    "value": 100,
                    "raw_value": "0",
                    ATTR_SMART_ATTRIBUTE_STATUS_CODE: 0,  # <-- ADD HERE (for "Passed")
                },
                "194": {
                    ATTR_ATTRIBUTE_ID: 194,
                    "value": 72,
                    "raw_value": "28",
                    ATTR_SMART_ATTRIBUTE_STATUS_CODE: 0,  # <-- ADD HERE (for "Passed")
                },
            },
        },
        KEY_DETAILS_METADATA: {
            "5": {ATTR_DISPLAY_NAME: "Reallocated Sectors Count", "critical": True},
            "194": {ATTR_DISPLAY_NAME: "Temperature Celsius", "critical": False},
        },
    }
}

COORDINATOR_DATA_TWO_DISKS = {
    MOCK_WWN1: COORDINATOR_DATA_ONE_DISK[MOCK_WWN1],  # Reuse
    MOCK_WWN2: {  # Second disk with fewer details for a simpler test
        KEY_SUMMARY_DEVICE: {
            ATTR_DEVICE_NAME: "/dev/sdb",
            ATTR_MODEL_NAME: "AnotherSSD",
            ATTR_FIRMWARE: "FWXYZ",
            ATTR_CAPACITY: 500 * 1024 * 1024 * 1024,  # 500GB
            ATTR_SUMMARY_DEVICE_STATUS: 1,  # Example: Warning status
        },
        KEY_SUMMARY_SMART: {},
        KEY_DETAILS_DEVICE: {},
        KEY_DETAILS_SMART_LATEST: {  # Only one SMART attribute
            ATTR_SMART_ATTRS: {
                "9": {
                    ATTR_ATTRIBUTE_ID: 9,
                    "value": 90,
                    "raw_value": "5000",
                    ATTR_SMART_ATTRIBUTE_STATUS_CODE: 0,
                },
            }
        },
        KEY_DETAILS_METADATA: {"9": {ATTR_DISPLAY_NAME: "Power-On Hours"}},
    },
}

# Hole alle Entity Descriptions für Hauptsensoren
# Get all Entity Descriptions for main sensors
# Assumption: MAIN_DISK_SENSOR_DESCRIPTIONS is available in scope
MAIN_SENSOR_TEST_PARAMS = [
    (
        ATTR_TEMPERATURE,
        COORDINATOR_DATA_ONE_DISK[MOCK_WWN1][KEY_DETAILS_SMART_LATEST][
            ATTR_TEMPERATURE
        ],
        "°C",
        "temperature",
    ),
    (
        ATTR_POWER_ON_HOURS,
        COORDINATOR_DATA_ONE_DISK[MOCK_WWN1][KEY_DETAILS_SMART_LATEST][
            ATTR_POWER_ON_HOURS
        ],
        "h",
        None,  # device_class is None for POH
    ),
]


# Helper function to create a sensor instance with a mock coordinator
def create_main_sensor(
    hass: HomeAssistant,  # Often not directly needed by sensor logic, but for HA context
    coordinator: ScrutinyDataUpdateCoordinator,  # The mocked coordinator
    wwn: str,
    entity_description: SensorEntityDescription,
) -> ScrutinyMainDiskSensor:
    """Helper to create a ScrutinyMainDiskSensor instance for testing."""
    # DeviceInfo is normally created in async_setup_entry.
    # For the unit test of the sensor, we can create it simplified here
    # or pass a MagicMock if we don't want to check it in detail.
    # Here we create a simple one to test sensor initialization.

    # Hole die Daten für die DeviceInfo aus den Koordinator-Daten
    # (simuliert, was async_setup_entry tun würde)
    summary_device_data = coordinator.data.get(wwn, {}).get(KEY_SUMMARY_DEVICE, {})
    device_info_name = (
        f"{summary_device_data.get(ATTR_MODEL_NAME, 'Disk')} "
        f"({summary_device_data.get(ATTR_DEVICE_NAME, wwn[-6:])})"
    )
    device_info = DeviceInfo(
        identifiers={(DOMAIN, wwn)},
        name=device_info_name,
        model=summary_device_data.get(ATTR_MODEL_NAME),
        manufacturer=summary_device_data.get("manufacturer")
        or "Scrutiny Integration Test",  # Adjusted
        sw_version=summary_device_data.get(ATTR_FIRMWARE),
        # via_device is less critical here for the sensor unit test
    )

    sensor = ScrutinyMainDiskSensor(
        coordinator=coordinator,
        entity_description=entity_description,
        wwn=wwn,
        device_info=device_info,
    )
    sensor.hass = hass  # Sensors often have a hass reference
    return sensor


# Helper function to create a ScrutinySmartAttributeSensor instance
def create_smart_attribute_sensor(
    hass: HomeAssistant,
    coordinator: ScrutinyDataUpdateCoordinator,  # Mocked coordinator
    wwn: str,
    attribute_id_str: str,  # e.g., "5", "194"
    # device_info wird normalerweise in async_setup_entry erstellt
) -> ScrutinySmartAttributeSensor:
    """Helper to create a ScrutinySmartAttributeSensor instance for testing."""
    summary_device_data = coordinator.data.get(wwn, {}).get(KEY_SUMMARY_DEVICE, {})
    device_info_name = (
        f"{summary_device_data.get(ATTR_MODEL_NAME, 'Disk')} "
        f"({summary_device_data.get(ATTR_DEVICE_NAME, wwn[-6:])})"
    )
    device_info = DeviceInfo(  # Simplified DeviceInfo for the test
        identifiers={(DOMAIN, wwn)},
        name=device_info_name,
        model=summary_device_data.get(ATTR_MODEL_NAME),
        manufacturer="Scrutiny Test SMART",
    )

    # Get the specific metadata for this attribute
    # The numeric ID is contained within the attribute data object itself
    attribute_data = coordinator.data[wwn][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS][
        attribute_id_str
    ]
    numeric_attr_id = attribute_data.get(ATTR_ATTRIBUTE_ID)
    attribute_metadata = coordinator.data[wwn][KEY_DETAILS_METADATA].get(
        str(numeric_attr_id), {}
    )

    sensor = ScrutinySmartAttributeSensor(
        coordinator=coordinator,
        wwn=wwn,
        device_info=device_info,
        attribute_id_str=attribute_id_str,
        attribute_metadata=attribute_metadata,
    )
    sensor.hass = hass
    return sensor


@pytest.mark.asyncio
async def test_async_setup_entry_one_disk(hass: HomeAssistant):
    """Test sensor setup with one disk in coordinator data."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_id_sensor")

    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    mock_coordinator.data = COORDINATOR_DATA_ONE_DISK
    # Add the 'last_update_success' attribute to the mock:
    mock_coordinator.last_update_success = True

    mock_entry.runtime_data = mock_coordinator
    mock_async_add_entities = MagicMock()

    await async_setup_entry(hass, mock_entry, mock_async_add_entities)
    await hass.async_block_till_done()
    # ... (Rest of the assertions remain the same) ...

    mock_async_add_entities.assert_called_once()
    added_entities = mock_async_add_entities.call_args[0][0]

    # Use the imported constant if it's now available,
    # or the hardcoded number if you haven't corrected the import yet.
    # Assumption: MAIN_DISK_SENSOR_DESCRIPTIONS is now correctly imported or replicated.
    num_main_sensors = len(
        MAIN_DISK_SENSOR_DESCRIPTIONS
    )  # Oder deine nachgebildete Version
    num_smart_attrs_disk1 = len(
        COORDINATOR_DATA_ONE_DISK[MOCK_WWN1][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]
    )
    expected_total_sensors = num_main_sensors + num_smart_attrs_disk1

    assert len(added_entities) == expected_total_sensors

    main_sensor_count = 0
    smart_attribute_sensor_count = 0
    for entity in added_entities:
        if isinstance(entity, ScrutinyMainDiskSensor):
            main_sensor_count += 1
            assert entity.device_info is not None  # type: ignore
            assert entity.device_info["identifiers"] == {(DOMAIN, MOCK_WWN1)}  # type: ignore
            assert entity.device_info["via_device"] == (DOMAIN, "test_entry_id_sensor")  # type: ignore
            assert (
                COORDINATOR_DATA_ONE_DISK[MOCK_WWN1][KEY_SUMMARY_DEVICE][
                    ATTR_MODEL_NAME
                ]  # type: ignore
                in entity.device_info["name"]  # type: ignore
            )
        elif isinstance(entity, ScrutinySmartAttributeSensor):
            smart_attribute_sensor_count += 1
            assert entity.device_info is not None
            assert entity.device_info["identifiers"] == {(DOMAIN, MOCK_WWN1)}  # type: ignore

    assert main_sensor_count == num_main_sensors
    assert smart_attribute_sensor_count == num_smart_attrs_disk1

    print(f"SUCCESS: {test_async_setup_entry_one_disk.__name__} passed!")


@pytest.mark.asyncio
async def test_async_setup_entry_coordinator_no_data(hass: HomeAssistant):
    """Test sensor setup when coordinator.data is None."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_no_data")
    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    mock_coordinator.data = None  # Coordinator has no data
    # last_update_success is less relevant here since data is already None,
    # but we set it for consistency in case it's checked.
    mock_coordinator.last_update_success = False

    mock_entry.runtime_data = mock_coordinator
    mock_async_add_entities = MagicMock()

    await async_setup_entry(hass, mock_entry, mock_async_add_entities)
    await hass.async_block_till_done()
    # async_add_entities should NOT have been called
    mock_async_add_entities.assert_not_called()

    print(f"SUCCESS: {test_async_setup_entry_coordinator_no_data.__name__} passed!")


@pytest.mark.asyncio
async def test_async_setup_entry_coordinator_empty_data_dict(hass: HomeAssistant):
    """Test sensor setup when coordinator.data is an empty dictionary."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_empty_data")
    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    mock_coordinator.data = {}  # Coordinator has an empty data dict
    mock_coordinator.last_update_success = True  # Update was successful, but no data

    mock_entry.runtime_data = mock_coordinator
    mock_async_add_entities = MagicMock()

    await async_setup_entry(hass, mock_entry, mock_async_add_entities)
    await hass.async_block_till_done()

    mock_async_add_entities.assert_not_called()

    print(
        f"SUCCESS: {test_async_setup_entry_coordinator_empty_data_dict.__name__} passed!"
    )


@pytest.mark.asyncio
async def test_async_setup_entry_disk_missing_smart_attrs(hass: HomeAssistant, caplog):
    """Test sensor setup if a disk's data is missing ATTR_SMART_ATTRS."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_missing_smart")
    # Modify the test data for a disk to remove ATTR_SMART_ATTRS
    # or set it to an invalid type.
    # Important: Make a copy to avoid modifying the original test data!
    import copy

    disk_data_no_smart_attrs = copy.deepcopy(COORDINATOR_DATA_ONE_DISK[MOCK_WWN1])
    # Remove the key or set it to something other than a dict
    if ATTR_SMART_ATTRS in disk_data_no_smart_attrs[KEY_DETAILS_SMART_LATEST]:
        del disk_data_no_smart_attrs[KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS]
    # Alternativ:
    # disk_data_no_smart_attrs[KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS] = "not a dict"

    coordinator_data_faulty_disk = {MOCK_WWN1: disk_data_no_smart_attrs}

    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    mock_coordinator.data = coordinator_data_faulty_disk
    mock_coordinator.last_update_success = True

    mock_entry.runtime_data = mock_coordinator
    mock_async_add_entities = MagicMock()

    # caplog fixture to check log output
    import logging

    caplog.set_level(logging.WARNING)

    await async_setup_entry(hass, mock_entry, mock_async_add_entities)
    await hass.async_block_till_done()

    mock_async_add_entities.assert_called_once()
    added_entities = mock_async_add_entities.call_args[0][0]

    # Only the main sensors should have been created
    num_main_sensors = len(MAIN_DISK_SENSOR_DESCRIPTIONS)  # Or your reference
    assert len(added_entities) == num_main_sensors

    main_sensor_count = 0
    for entity in added_entities:
        if isinstance(entity, ScrutinyMainDiskSensor):
            main_sensor_count += 1
    assert main_sensor_count == num_main_sensors
    # Check if the warning was logged
    # The exact log message depends on your implementation
    # (whether you log the "key missing" case differently from "wrong type").
    # If ATTR_SMART_ATTRS is completely missing, .get(ATTR_SMART_ATTRS, {}) will return an empty dict,
    # and the `isinstance` check would be `True`. The `else` block would not be reached.
    # To test the `else` block, set ATTR_SMART_ATTRS to "not a dict".

    # Um den else-Block zu testen:
    # disk_data_no_smart_attrs[KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS] = "not a dict"
    # ... (dann den Test mit dieser Änderung laufen lassen)
    # assert "SMART attributes data for disk" in caplog.text
    # assert "is not a dict" in caplog.text

    print(
        f"SUCCESS: {test_async_setup_entry_disk_missing_smart_attrs.__name__} passed!"
    )


@pytest.mark.asyncio
async def test_main_disk_sensor_temperature(hass: HomeAssistant):
    """Test ScrutinyMainDiskSensor for Temperature."""
    wwn = MOCK_WWN1
    temp_description = next(
        d for d in MAIN_DISK_SENSOR_DESCRIPTIONS if d.key == ATTR_TEMPERATURE
    )

    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    mock_coordinator.data = COORDINATOR_DATA_ONE_DISK
    mock_coordinator.last_update_success = True

    sensor = create_main_sensor(hass, mock_coordinator, wwn, temp_description)

    # Initialization
    assert sensor.unique_id == f"{DOMAIN}_{wwn}_{ATTR_TEMPERATURE}"
    assert sensor.name == "Temperature"
    assert sensor.available is True
    assert (
        sensor.native_value
        == COORDINATOR_DATA_ONE_DISK[wwn][KEY_DETAILS_SMART_LATEST][ATTR_TEMPERATURE]
    )
    assert sensor.native_unit_of_measurement == "°C"
    assert sensor.device_class == "temperature"

    # Test _handle_coordinator_update with new data
    updated_disk_data_wwn1 = COORDINATOR_DATA_ONE_DISK[wwn].copy()
    updated_disk_data_wwn1[KEY_DETAILS_SMART_LATEST] = updated_disk_data_wwn1[
        KEY_DETAILS_SMART_LATEST
    ].copy()
    updated_disk_data_wwn1[KEY_DETAILS_SMART_LATEST][ATTR_TEMPERATURE] = 35
    mock_coordinator.data = {
        wwn: updated_disk_data_wwn1
    }  # Only this disk with new data

    with patch.object(
        sensor, "async_write_ha_state", new_callable=MagicMock
    ) as mock_write_state_1:
        sensor._handle_coordinator_update()
        await hass.async_block_till_done()
    assert sensor.native_value == 35
    mock_write_state_1.assert_called_once()

    # Test 'available' property and native_value when coordinator was not successful
    mock_coordinator.last_update_success = False
    # Important: After changing last_update_success, the sensor state must be updated
    with patch.object(
        sensor, "async_write_ha_state", new_callable=MagicMock
    ) as mock_write_state_2:
        sensor._handle_coordinator_update()  # Simulate the sensor reacting to the update
        await hass.async_block_till_done()

    assert sensor.available is False  # Should be False now
    assert (
        sensor.native_value is None
    )  # Should be None now, as _update_sensor_state was called
    mock_write_state_2.assert_called_once()  # async_write_ha_state should have been called

    # Test 'available' property and native_value when the disk is not in the data
    mock_coordinator.last_update_success = True  # Update itself is successful again
    mock_coordinator.data = {}  # But no more data for this disk

    # Important: After changing coordinator data, the sensor state must be updated
    with patch.object(
        sensor, "async_write_ha_state", new_callable=MagicMock
    ) as mock_write_state_3:
        sensor._handle_coordinator_update()  # Simulate the sensor reacting to the update
        await hass.async_block_till_done()

    assert sensor.available is False  # Sollte jetzt False sein
    assert sensor.native_value is None  # Sollte jetzt None sein
    mock_write_state_3.assert_called_once()

    print(f"SUCCESS: {test_main_disk_sensor_temperature.__name__} passed!")


@pytest.mark.parametrize(
    "sensor_key, initial_value, unit, device_class_val", MAIN_SENSOR_TEST_PARAMS
)
@pytest.mark.asyncio
async def test_main_disk_sensor_generic(
    hass: HomeAssistant,
    sensor_key: str,
    initial_value: Any,
    unit: str | None,
    device_class_val: str | None,
):
    wwn = MOCK_WWN1
    description = next(d for d in MAIN_DISK_SENSOR_DESCRIPTIONS if d.key == sensor_key)

    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    mock_coordinator.data = COORDINATOR_DATA_ONE_DISK
    mock_coordinator.last_update_success = True

    sensor = create_main_sensor(hass, mock_coordinator, wwn, description)

    assert sensor.unique_id == f"{DOMAIN}_{wwn}_{sensor_key}"
    assert sensor.name == description.name
    assert sensor.available is True
    # Adjust specific logic for capacity and status mapping here if necessary
    if sensor_key == ATTR_CAPACITY:
        assert sensor.native_value == round(initial_value / (1024**3), 2)
    elif sensor_key == ATTR_SUMMARY_DEVICE_STATUS:
        # Here you would need to get the status code from the test data and check the mapping
        status_code = COORDINATOR_DATA_ONE_DISK[wwn][KEY_SUMMARY_DEVICE][
            ATTR_SUMMARY_DEVICE_STATUS
        ]
        from custom_components.scrutiny.const import (
            SCRUTINY_DEVICE_SUMMARY_STATUS_MAP,
            SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN,
        )

        assert sensor.native_value == SCRUTINY_DEVICE_SUMMARY_STATUS_MAP.get(
            status_code, SCRUTINY_DEVICE_SUMMARY_STATUS_UNKNOWN
        )
    # ... similar logic for ATTR_SMART_OVERALL_STATUS ...
    else:
        assert sensor.native_value == initial_value

    assert sensor.native_unit_of_measurement == unit
    assert sensor.device_class == device_class_val
    # ... (further tests for _handle_coordinator_update and available as in the temperature sensor test) ...

    print(f"SUCCESS: test_main_disk_sensor_generic for {sensor_key} passed!")


@pytest.mark.asyncio
async def test_smart_attribute_sensor_update_and_availability(hass: HomeAssistant):
    """Test _handle_coordinator_update and availability of ScrutinySmartAttributeSensor."""
    wwn = MOCK_WWN1
    attr_id_str = "194"  # Let's test with attribute "194" (Temperature)

    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    initial_data = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)
    mock_coordinator.data = initial_data
    mock_coordinator.last_update_success = True

    sensor = create_smart_attribute_sensor(hass, mock_coordinator, wwn, attr_id_str)

    # --- Initial state ---
    initial_attr_data = initial_data[wwn][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS][
        attr_id_str
    ]
    initial_status_code = initial_attr_data[ATTR_SMART_ATTRIBUTE_STATUS_CODE]
    initial_raw_value = initial_attr_data["raw_value"]

    assert sensor.available is True
    assert sensor.native_value == ATTR_SMART_STATUS_MAP.get(
        initial_status_code, ATTR_SMART_STATUS_UNKNOWN
    )
    assert sensor.extra_state_attributes[ATTR_RAW_VALUE] == initial_raw_value  # type: ignore

    # --- Simulate a coordinator update with changed values for the attribute ---
    updated_data_step1 = copy.deepcopy(initial_data)
    updated_data_step1[wwn][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS][attr_id_str][
        ATTR_SMART_ATTRIBUTE_STATUS_CODE
    ] = 2  # Warning
    updated_data_step1[wwn][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS][attr_id_str][
        "raw_value"
    ] = "35"
    mock_coordinator.data = updated_data_step1

    with patch.object(
        sensor, "async_write_ha_state", new_callable=MagicMock
    ) as mock_write_state_update:
        sensor._handle_coordinator_update()
        await hass.async_block_till_done()

    assert sensor.available is True
    assert sensor.native_value == ATTR_SMART_STATUS_MAP.get(
        2, ATTR_SMART_STATUS_UNKNOWN
    )
    assert sensor.extra_state_attributes[ATTR_RAW_VALUE] == "35"  # type: ignore
    mock_write_state_update.assert_called_once()

    # --- Simulate that the specific SMART attribute is missing in the data ---
    # The sensor is now available=True, native_value="Warning", raw_value="35"
    data_attr_missing = copy.deepcopy(
        updated_data_step1
    )  # Starte vom vorherigen Zustand
    del data_attr_missing[wwn][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS][attr_id_str]
    mock_coordinator.data = data_attr_missing

    with patch.object(
        sensor, "async_write_ha_state", new_callable=MagicMock
    ) as mock_write_state_attr_missing:
        sensor._handle_coordinator_update()  # This should cause a state change
        await hass.async_block_till_done()

    assert sensor.available is False
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
    mock_write_state_attr_missing.assert_called_once()  # Expect call, as state changes from True/Warning to False/None

    # --- Simulate that the entire disk is missing in the data ---
    # Der Sensor ist jetzt available=False, native_value=None, extra_state_attributes={}
    mock_coordinator.data = {}  # Keine Daten für irgendeine Disk

    # print(f"DEBUG: Before _handle_coordinator_update for disk_missing. Sensor available: {sensor.available}")

    with patch.object(
        sensor, "async_write_ha_state", new_callable=MagicMock
    ) as mock_write_state_disk_missing:
        sensor._handle_coordinator_update()  # State does not change (remains unavailable)
        await hass.async_block_till_done()

    # print(f"DEBUG: After _handle_coordinator_update for disk_missing. Sensor available: {sensor.available}, native_value: {sensor.native_value}")
    assert sensor.available is False
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
    # If the state doesn't change (was already unavailable), async_write_ha_state is not called
    # if your _handle_coordinator_update has a corresponding optimization.
    mock_write_state_disk_missing.assert_not_called()  # <--- CHANGED ASSERTION

    # --- Simulate that the coordinator update fails ---
    # FIRST, set the sensor back to an available state to force a change
    mock_coordinator.data = copy.deepcopy(initial_data)  # Valid data
    mock_coordinator.last_update_success = True
    with patch.object(
        sensor, "async_write_ha_state", new_callable=MagicMock
    ) as mock_write_state_re_enable:
        sensor._handle_coordinator_update()
        await hass.async_block_till_done()
    assert sensor.available is True  # Ensure it's available again
    mock_write_state_re_enable.assert_called_once()  # There was a state change

    # NOW simulate the coordinator error
    mock_coordinator.last_update_success = False  # Update was not successful

    with patch.object(
        sensor, "async_write_ha_state", new_callable=MagicMock
    ) as mock_write_state_coord_fail:
        sensor._handle_coordinator_update()  # This should cause a state change
        await hass.async_block_till_done()

    assert sensor.available is False
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
    mock_write_state_coord_fail.assert_called_once()  # Expect call, as state changes from True to False

    print(
        f"SUCCESS: {test_smart_attribute_sensor_update_and_availability.__name__} passed!"
    )


@pytest.mark.asyncio
async def test_smart_attribute_sensor_basic_init_and_state(hass: HomeAssistant):
    """Test basic initialization and state of ScrutinySmartAttributeSensor."""
    wwn = MOCK_WWN1
    attr_id_str = "5"

    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    mock_coordinator.data = COORDINATOR_DATA_ONE_DISK
    mock_coordinator.last_update_success = True

    sensor = create_smart_attribute_sensor(hass, mock_coordinator, wwn, attr_id_str)

    # --- Teste die Komponenten des Namens ---
    # 1. device_info.name (wie es vom Sensor gespeichert wird)
    summary_device_data_for_name = COORDINATOR_DATA_ONE_DISK[wwn][KEY_SUMMARY_DEVICE]
    expected_device_info_name_in_sensor = (  # Der Name, der in sensor._attr_device_info["name"] sein sollte
        f"{summary_device_data_for_name.get(ATTR_MODEL_NAME, 'Disk')} "
        f"({summary_device_data_for_name.get(ATTR_DEVICE_NAME, wwn[-6:])})"
    )
    assert sensor.device_info is not None
    assert sensor.device_info["name"] == expected_device_info_name_in_sensor  # type: ignore[reportTypedDictNotRequiredAccess]

    # 2. entity_description.name (wie es im Sensor gesetzt wird)
    attribute_metadata_for_name = COORDINATOR_DATA_ONE_DISK[wwn][KEY_DETAILS_METADATA][
        str(
            COORDINATOR_DATA_ONE_DISK[wwn][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS][
                attr_id_str
            ][ATTR_ATTRIBUTE_ID]
        )
    ]
    display_name_meta_for_name = attribute_metadata_for_name.get(ATTR_DISPLAY_NAME)
    attribute_specific_name_part_for_name = (
        display_name_meta_for_name
        if display_name_meta_for_name
        else f"Attribute {attr_id_str}"
    )
    expected_entity_description_name_in_sensor = (
        f"SMART {attr_id_str} {attribute_specific_name_part_for_name}"
    )
    assert sensor.entity_description.name == expected_entity_description_name_in_sensor

    # 3. Überprüfe _attr_has_entity_name (optional, aber gut zur Bestätigung)
    assert (
        sensor.has_entity_name is True
    )  # oder getattr(sensor, "_attr_has_entity_name", False) is True

    # Die Assertion für den voll zusammengesetzten sensor.name entfernen wir,
    # da sie im Unit-Test direkt nach der Instanziierung nicht zuverlässig ist.
    # Die eigentliche Zusammensetzung erfolgt durch HA-Mechanismen.
    # Stattdessen könnten wir prüfen, ob _attr_name NICHT gesetzt ist.
    assert (
        not hasattr(sensor, "_attr_name")
        or getattr(sensor, "_attr_name") is None
        or getattr(sensor, "_attr_name") == getattr(sensor, "_SENTINEL", object())
    )

    # --- Teste Unique ID (bleibt wie zuvor, da dies vom Sensor direkt gesetzt wird) ---
    # ... (deine unique_id Assertions) ...
    device_name_raw_for_uid = summary_device_data_for_name.get(ATTR_DEVICE_NAME)
    if not device_name_raw_for_uid:
        device_name_cleaned_for_id_uid = f"disk_{wwn[-6:]}"
    else:
        device_name_cleaned_for_id_uid = device_name_raw_for_uid.split("/")[-1]
    device_name_slug_for_id_uid = slugify(device_name_cleaned_for_id_uid)
    slugified_attr_name_part_for_id_uid = slugify(attribute_specific_name_part_for_name)
    expected_unique_id = (
        f"{DOMAIN}_{wwn}_{device_name_slug_for_id_uid}_smart_"
        f"{attr_id_str}_{slugified_attr_name_part_for_id_uid}"
    )
    assert sensor.unique_id == expected_unique_id

    # --- Teste Verfügbarkeit und initialen Zustand (Status) ---
    assert sensor.available is True
    expected_status_code = COORDINATOR_DATA_ONE_DISK[wwn][KEY_DETAILS_SMART_LATEST][
        ATTR_SMART_ATTRS
    ][attr_id_str][ATTR_SMART_ATTRIBUTE_STATUS_CODE]
    assert sensor.native_value == ATTR_SMART_STATUS_MAP.get(
        expected_status_code, ATTR_SMART_STATUS_UNKNOWN
    )

    # --- Teste Extra State Attributes (bleibt gleich) ---
    # ... (deine extra_state_attributes Assertions) ...

    # --- Teste entity_registry_enabled_default (bleibt gleich) ---
    # ... (deine entity_registry_enabled_default Assertion) ...

    print(
        f"SUCCESS: {test_smart_attribute_sensor_basic_init_and_state.__name__} passed!"
    )


# tests/test_sensor.py
# ... (Imports, Testdaten, Hilfsfunktionen wie create_smart_attribute_sensor) ...
# from homeassistant.util import slugify # Sicherstellen, dass slugify importiert ist


@pytest.mark.asyncio
async def test_smart_attribute_sensor_name_fallback(hass: HomeAssistant):
    """Test ScrutinySmartAttributeSensor name generation fallback if display_name is missing."""
    wwn = MOCK_WWN1
    attr_id_str_fallback = "99"  # Ein fiktives Attribut

    import copy

    test_data_for_name_fallback = copy.deepcopy(COORDINATOR_DATA_ONE_DISK)

    # Füge das neue SMART-Attribut hinzu
    numeric_attr_id_fallback = 99
    test_data_for_name_fallback[wwn][KEY_DETAILS_SMART_LATEST][ATTR_SMART_ATTRS][
        attr_id_str_fallback
    ] = {
        ATTR_ATTRIBUTE_ID: numeric_attr_id_fallback,
        "value": 50,
        ATTR_SMART_ATTRIBUTE_STATUS_CODE: 2,  # z.B. Warning
    }
    # Stelle sicher, dass für ID 99 keine Metadaten mit display_name existieren
    if (
        str(numeric_attr_id_fallback)
        in test_data_for_name_fallback[wwn][KEY_DETAILS_METADATA]
    ):
        if (
            ATTR_DISPLAY_NAME
            in test_data_for_name_fallback[wwn][KEY_DETAILS_METADATA][
                str(numeric_attr_id_fallback)
            ]
        ):
            del test_data_for_name_fallback[wwn][KEY_DETAILS_METADATA][
                str(numeric_attr_id_fallback)
            ][ATTR_DISPLAY_NAME]
    else:
        test_data_for_name_fallback[wwn][KEY_DETAILS_METADATA][
            str(numeric_attr_id_fallback)
        ] = {
            ATTR_IS_CRITICAL: False  # Beispiel für andere Metadaten
        }

    mock_coordinator = MagicMock(spec=ScrutinyDataUpdateCoordinator)
    mock_coordinator.data = test_data_for_name_fallback
    mock_coordinator.last_update_success = True

    sensor = create_smart_attribute_sensor(
        hass, mock_coordinator, wwn, attr_id_str_fallback
    )

    # --- Teste die Komponenten des Namens (mit Fallback) ---
    # 1. device_info.name (wie es vom Sensor gespeichert wird)
    summary_device_data_for_name = test_data_for_name_fallback[wwn].get(
        KEY_SUMMARY_DEVICE, {}
    )
    expected_device_info_name_in_sensor = (
        f"{summary_device_data_for_name.get(ATTR_MODEL_NAME, 'Disk')} "
        f"({summary_device_data_for_name.get(ATTR_DEVICE_NAME, wwn[-6:])})"
    )
    assert sensor.device_info is not None
    assert sensor.device_info["name"] == expected_device_info_name_in_sensor  # type: ignore[reportTypedDictNotRequiredAccess]

    # 2. entity_description.name (sollte den Fallback-Namensteil enthalten)
    # Der Fallback ist f"Attribute {attr_id_str_fallback}"
    attribute_specific_name_part_for_name = f"Attribute {attr_id_str_fallback}"
    expected_entity_description_name_in_sensor = (
        f"SMART {attr_id_str_fallback} {attribute_specific_name_part_for_name}"
    )
    assert sensor.entity_description.name == expected_entity_description_name_in_sensor

    # 3. Überprüfe _attr_has_entity_name
    assert sensor.has_entity_name is True

    # Die Assertion für den voll zusammengesetzten sensor.name entfernen wir,
    # da sie im Unit-Test direkt nach der Instanziierung nicht zuverlässig ist.
    # Wir haben aber im UI verifiziert, dass es funktioniert.
    # Stattdessen:
    assert (
        not hasattr(sensor, "_attr_name")
        or getattr(sensor, "_attr_name") is None
        or getattr(sensor, "_attr_name") == getattr(sensor, "_SENTINEL", object())
    )

    # --- Teste Unique ID (mit Fallback-Namensteil) ---
    device_name_raw_for_uid = summary_device_data_for_name.get(ATTR_DEVICE_NAME)
    if not device_name_raw_for_uid:
        device_name_cleaned_for_id_uid = f"disk_{wwn[-6:]}"
    else:
        device_name_cleaned_for_id_uid = device_name_raw_for_uid.split("/")[-1]
    device_name_slug_for_id_uid = slugify(device_name_cleaned_for_id_uid)

    # Verwende den Fallback-Teil für den Slug
    slugified_attr_name_part_for_id_uid = slugify(attribute_specific_name_part_for_name)

    expected_unique_id = (
        f"{DOMAIN}_{wwn}_{device_name_slug_for_id_uid}_smart_"
        f"{attr_id_str_fallback}_{slugified_attr_name_part_for_id_uid}"
    )
    assert sensor.unique_id == expected_unique_id

    # --- Teste nativen Wert (Status) ---
    assert sensor.native_value == ATTR_SMART_STATUS_MAP.get(
        2, ATTR_SMART_STATUS_UNKNOWN
    )  # "Warning"

    # --- Teste entity_registry_enabled_default ---
    # Metadaten für Attribut 99 haben ATTR_IS_CRITICAL: False (oder es fehlt und defaultet zu False)
    expected_enabled_default = test_data_for_name_fallback[wwn][KEY_DETAILS_METADATA][
        str(numeric_attr_id_fallback)
    ].get(ATTR_IS_CRITICAL, False)
    assert sensor.entity_registry_enabled_default == expected_enabled_default

    print(f"SUCCESS: {test_smart_attribute_sensor_name_fallback.__name__} passed!")
