import pytest
from unittest.mock import (
    patch,
    AsyncMock,
    MagicMock,
)  # MagicMock for more complex mocks

import asyncio  # For asyncio.gather simulation

from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.core import (
    HomeAssistant,
)  # For type hinting, provided by fixture

# Class and exceptions to be tested
from custom_components.scrutiny.coordinator import ScrutinyDataUpdateCoordinator
from custom_components.scrutiny.api import (
    ScrutinyApiClient,  # Will be mocked
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
    # ScrutinyApiAuthError, # Depending on whether we want to test it
)

# Konstanten, die der Koordinator verwendet
from custom_components.scrutiny.const import (
    LOGGER,  # Kann auch gemockt werden
    DOMAIN,
    ATTR_DEVICE,
    ATTR_SMART,
    ATTR_METADATA,
    ATTR_SMART_RESULTS,
    KEY_SUMMARY_DEVICE,
    KEY_SUMMARY_SMART,
    KEY_DETAILS_DEVICE,
    KEY_DETAILS_SMART_LATEST,
    KEY_DETAILS_METADATA,
)

from datetime import timedelta

# Define constants for capacity calculation FIRST
TB_IN_BYTES = 1024 * 1024 * 1024 * 1024  # 1 Terabyte in Bytes

# What api_client.async_get_summary() returns
MOCK_API_SUMMARY_DATA = {
    "wwn1": {
        ATTR_DEVICE: {"device_name": "/dev/sda", "model_name": "DiskModelA_Sum"},
        ATTR_SMART: {"temp": 30, "power_on_hours": 1000},
    },
    "wwn2": {
        ATTR_DEVICE: {"device_name": "/dev/sdb", "model_name": "DiskModelB_Sum"},
        ATTR_SMART: {"temp": 35, "power_on_hours": 2000},
    },
}

# What api_client.async_get_device_details("wwn1") returns
MOCK_API_DETAILS_DATA_WWN1 = {
    "success": True,
    "data": {
        ATTR_DEVICE: {
            "device_name": "/dev/sda",
            "model_name": "DiskModelA_Det",
            "capacity": 1 * TB_IN_BYTES,  # Use the defined constant
        },
        ATTR_SMART_RESULTS: [
            {
                "attrs": {"5": {"attribute_id": 5, "value": 100}},
                "Status": 0,
                "temp": 31,
                "power_on_hours": 1001,
            }
        ],
    },
    ATTR_METADATA: {"5": {"display_name": "Reallocated Sectors Count"}},
}

# What api_client.async_get_device_details("wwn2") returns
MOCK_API_DETAILS_DATA_WWN2 = {
    "success": True,
    "data": {
        ATTR_DEVICE: {
            "device_name": "/dev/sdb",
            "model_name": "DiskModelB_Det",
            "capacity": 2 * TB_IN_BYTES,  # Use the defined constant
        },
        ATTR_SMART_RESULTS: [
            {
                "attrs": {"194": {"attribute_id": 194, "value": 36}},
                "Status": 0,
                "temp": 36,
                "power_on_hours": 2002,
            }
        ],
    },
    ATTR_METADATA: {"194": {"display_name": "Temperature Celsius"}},
}


# --- Helper function to create a coordinator mock ---
async def create_mocked_coordinator(
    hass: HomeAssistant,  # Provided by pytest-homeassistant-custom-component
    mock_api_client: AsyncMock,  # An already configured mock for ScrutinyApiClient
) -> ScrutinyDataUpdateCoordinator:
    """Helper to create a ScrutinyDataUpdateCoordinator with a mocked API client."""
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,  # You could also pass a MagicMock() for the logger here
        name=f"{DOMAIN}-test-coordinator",
        api_client=mock_api_client,
        update_interval=timedelta(
            seconds=30
        ),  # Irrelevant for manual updates in the test
    )
    return coordinator


@pytest.mark.asyncio
async def test_coordinator_async_update_data_success(hass: HomeAssistant):
    # ... (Mock setup remains the same) ...
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    mock_api_client.async_get_summary = AsyncMock(return_value=MOCK_API_SUMMARY_DATA)

    async def mock_details_side_effect(wwn):
        if wwn == "wwn1":
            return MOCK_API_DETAILS_DATA_WWN1
        if wwn == "wwn2":
            return MOCK_API_DETAILS_DATA_WWN2
        return {}

    mock_api_client.async_get_device_details = AsyncMock(
        side_effect=mock_details_side_effect
    )

    coordinator = await create_mocked_coordinator(hass, mock_api_client)

    # 4. Execute the method to be tested -> Use async_refresh()
    # updated_data = await coordinator._async_update_data() # Old method
    await (
        coordinator.async_refresh()
    )  # NEW METHOD: Triggers update and sets coordinator.data

    # The data should now be in coordinator.data
    updated_data = coordinator.data  # Get the data from the instance variable

    # 5. Check the calls on the mock API client (remains the same)
    mock_api_client.async_get_summary.assert_called_once()
    assert mock_api_client.async_get_device_details.call_count == len(
        MOCK_API_SUMMARY_DATA
    )
    mock_api_client.async_get_device_details.assert_any_call("wwn1")
    mock_api_client.async_get_device_details.assert_any_call("wwn2")
    # 6. Check the structure and content of the aggregated data (remains the same)
    assert updated_data is not None
    assert "wwn1" in updated_data
    # ... (Rest of the assertions for updated_data) ...

    # Die letzte Assertion ist jetzt implizit, da updated_data = coordinator.data ist
    # assert coordinator.data == updated_data # Diese Zeile ist jetzt nicht mehr nötig oder kann so bleiben

    print("SUCCESS: test_coordinator_async_update_data_success passed!")


@pytest.mark.asyncio
async def test_coordinator_update_fails_on_summary_connection_error(
    hass: HomeAssistant,
):
    """Test coordinator handles summary connection error and sets last_update_success to False."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    mock_api_client.async_get_summary = AsyncMock(
        side_effect=ScrutinyApiConnectionError("Simulated summary connection error")
    )
    mock_api_client.async_get_device_details = AsyncMock()

    coordinator = await create_mocked_coordinator(hass, mock_api_client)

    # Execute async_refresh. We do NOT necessarily expect it to throw UpdateFailed now,
    # but rather that it handles the error internally.
    # The DataUpdateCoordinator base class catches the exception from _async_update_data
    # (if it's not UpdateFailed) or UpdateFailed itself.
    # It logs the error and sets last_update_success.

    # We need to check if async_refresh itself throws an exception
    # that is not UpdateFailed, which should not happen.
    # If _async_update_data throws UpdateFailed, async_refresh will catch it and not re-throw.
    # If _async_update_data throws another exception, async_refresh will catch it and not re-throw.

    # Try to execute the refresh. It should not pass any exception to the test.
    await coordinator.async_refresh()

    # Check the status after the failed refresh
    assert coordinator.last_update_success is False  # <--- NEW MAIN ASSERTION

    # The original exception should be stored in the coordinator as self.last_exception
    # (or at least the UpdateFailed that was thrown by _raise_update_failed)
    assert coordinator.last_exception is not None
    # Check the type of the stored exception.
    # If your _async_update_data throws UpdateFailed, it should be UpdateFailed here.
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert "Connection error during Scrutiny data update cycle" in str(
        coordinator.last_exception
    )
    assert "Simulated summary connection error" in str(coordinator.last_exception)
    # Überprüfe die Mock-Aufrufe
    mock_api_client.async_get_summary.assert_called_once()
    mock_api_client.async_get_device_details.assert_not_called()

    # coordinator.data sollte nach einem fehlgeschlagenen ersten Update None sein
    assert coordinator.data is None

    print(
        "SUCCESS: test_coordinator_update_fails_on_summary_connection_error (checking last_update_success) passed!"
    )


@pytest.mark.asyncio
async def test_coordinator_handles_partial_detail_failure(hass: HomeAssistant):
    """Test coordinator handles failure for one disk's details but processes others."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)

    # Summary is successful
    mock_api_client.async_get_summary = AsyncMock(return_value=MOCK_API_SUMMARY_DATA)

    # Details for wwn1 are successful, for wwn2 it fails
    async def mock_details_side_effect_with_failure(wwn):
        if wwn == "wwn1":
            return MOCK_API_DETAILS_DATA_WWN1
        if wwn == "wwn2":
            # Simulate an error that _process_detail_results receives as an exception
            raise ScrutinyApiResponseError(
                "Simulated detail API response error for wwn2"
            )
        return {}  # Fallback, should not be reached with only two WWNs

    mock_api_client.async_get_device_details = AsyncMock(
        side_effect=mock_details_side_effect_with_failure
    )

    coordinator = await create_mocked_coordinator(hass, mock_api_client)

    # async_refresh should NOT throw an UpdateFailed exception here.
    # The error is handled in _process_detail_results.
    await coordinator.async_refresh()

    updated_data = coordinator.data
    assert updated_data is not None
    assert coordinator.last_update_success is True  # The overall update was successful

    # Überprüfe Aufrufe
    mock_api_client.async_get_summary.assert_called_once()
    assert mock_api_client.async_get_device_details.call_count == len(
        MOCK_API_SUMMARY_DATA
    )
    mock_api_client.async_get_device_details.assert_any_call("wwn1")
    mock_api_client.async_get_device_details.assert_any_call("wwn2")

    # Data for wwn1 should be complete
    assert "wwn1" in updated_data
    assert updated_data["wwn1"][KEY_SUMMARY_DEVICE]["model_name"] == "DiskModelA_Sum"
    assert updated_data["wwn1"][KEY_DETAILS_DEVICE]["model_name"] == "DiskModelA_Det"
    assert (
        updated_data["wwn1"][KEY_DETAILS_SMART_LATEST]["temp"] == 31
    )  # From MOCK_API_DETAILS_DATA_WWN1

    # Data for wwn2: Summary should be there, details should be empty
    # (according to your _process_detail_results logic, which sets empty dicts on exception)
    assert "wwn2" in updated_data
    assert updated_data["wwn2"][KEY_SUMMARY_DEVICE]["model_name"] == "DiskModelB_Sum"
    assert updated_data["wwn2"][KEY_DETAILS_DEVICE] == {}
    assert updated_data["wwn2"][KEY_DETAILS_SMART_LATEST] == {}
    assert updated_data["wwn2"][KEY_DETAILS_METADATA] == {}
    print("SUCCESS: test_coordinator_handles_partial_detail_failure passed!")


@pytest.mark.asyncio  # Nicht unbedingt async, wenn _process_detail_results nicht async ist
async def test_process_detail_results_handles_exception_input(hass: HomeAssistant):
    """Test _process_detail_results correctly handles an Exception as input."""
    # Create a dummy coordinator just for this method test
    # The API client mock is not strictly necessary here if _process_detail_results doesn't use it directly.
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name="test",
        api_client=mock_api_client,
        update_interval=timedelta(seconds=30),
    )

    wwn_key = "test_wwn_exception"
    # Simulate that asyncio.gather returned an exception for this task
    exception_input = ValueError("Simulated error during detail fetch")
    target_data_dict = {}  # The dictionary that the method should populate

    # Call the method directly
    coordinator._process_detail_results(wwn_key, exception_input, target_data_dict)

    # Check if the detail keys were populated with empty dictionaries
    assert target_data_dict[KEY_DETAILS_DEVICE] == {}
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}
    assert target_data_dict[KEY_DETAILS_METADATA] == {}
    # Optional: Check if a warning was logged (requires mocking the logger)


@pytest.mark.asyncio
async def test_process_detail_results_handles_valid_input(hass: HomeAssistant):
    """Test _process_detail_results correctly handles valid detail input."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name="test",
        api_client=mock_api_client,
        update_interval=timedelta(seconds=30),
    )
    wwn_key = "wwn1"
    # Use our MOCK_API_DETAILS_DATA_WWN1 as valid input
    valid_input = MOCK_API_DETAILS_DATA_WWN1
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, valid_input, target_data_dict)

    assert (
        target_data_dict[KEY_DETAILS_DEVICE]
        == MOCK_API_DETAILS_DATA_WWN1["data"][ATTR_DEVICE]
    )
    assert (
        target_data_dict[KEY_DETAILS_SMART_LATEST]
        == MOCK_API_DETAILS_DATA_WWN1["data"][ATTR_SMART_RESULTS][0]
    )
    assert (
        target_data_dict[KEY_DETAILS_METADATA]
        == MOCK_API_DETAILS_DATA_WWN1[ATTR_METADATA]
    )


@pytest.mark.asyncio
async def test_coordinator_handles_empty_summary(hass: HomeAssistant):
    """Test coordinator handles an empty summary (no disks)."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    mock_api_client.async_get_summary = AsyncMock(return_value={})  # Empty summary
    mock_api_client.async_get_device_details = AsyncMock()

    coordinator = await create_mocked_coordinator(hass, mock_api_client)
    await coordinator.async_refresh()

    assert coordinator.data == {}
    assert coordinator.last_update_success is True
    mock_api_client.async_get_summary.assert_called_once()
    mock_api_client.async_get_device_details.assert_not_called()  # Important!


@pytest.mark.asyncio
async def test_coordinator_handles_invalid_summary_type(hass: HomeAssistant):
    """Test coordinator handles summary data that is not a dictionary and sets last_update_success."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    mock_api_client.async_get_summary = AsyncMock(
        return_value="not a dict"  # Invalid type
    )
    mock_api_client.async_get_device_details = AsyncMock()

    coordinator = await create_mocked_coordinator(hass, mock_api_client)

    # Execute async_refresh. It should handle the error internally.
    await coordinator.async_refresh()

    # Check the status after the failed refresh
    assert coordinator.last_update_success is False

    assert coordinator.last_exception is not None
    assert isinstance(coordinator.last_exception, UpdateFailed)

    # The message from UpdateFailed is constructed by _raise_update_failed in the coordinator.
    # It contains the message of the ScrutinyApiError, which was the ScrutinyApiResponseError.
    # The original ScrutinyApiResponseError had the message "Summary data from API was not a dictionary."
    # The ScrutinyApiError block turns this into:
    # f"API error during Scrutiny data update cycle: {err!s}"
    # where err!s is then "Summary data from API was not a dictionary.".

    # Expected message in last_exception.args[0] or str(coordinator.last_exception)
    expected_msg_part_from_api_error = "Summary data from API was not a dictionary."
    expected_wrapper_msg = "API error during Scrutiny data update cycle"

    assert expected_wrapper_msg in str(coordinator.last_exception)
    assert expected_msg_part_from_api_error in str(coordinator.last_exception)

    # Check the cause of the UpdateFailed exception, it should be ScrutinyApiResponseError
    assert isinstance(coordinator.last_exception.__cause__, ScrutinyApiResponseError)
    assert expected_msg_part_from_api_error in str(coordinator.last_exception.__cause__)

    # Check mock calls
    mock_api_client.async_get_summary.assert_called_once()
    mock_api_client.async_get_device_details.assert_not_called()

    assert coordinator.data is None  # Da der erste Refresh fehlschlug

    print(
        "SUCCESS: test_coordinator_handles_invalid_summary_type (checking last_update_success) passed!"
    )


# --- Tests for _process_detail_results ---


def _get_dummy_coordinator_for_method_test(
    hass: HomeAssistant,
) -> ScrutinyDataUpdateCoordinator:
    """Helper to get a coordinator instance for testing its methods directly."""
    # The API client mock is often not critical here, as _process_detail_results
    # usually doesn't use it directly, only the data it would have provided.
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    return ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,  # Or a MagicMock() for the logger to check log output
        name="test_process_details",
        api_client=mock_api_client,
        update_interval=timedelta(seconds=30),
    )


# --- Tests für die Methode _process_detail_results ---
# --- Tests for the _process_detail_results method ---


def test_process_detail_results_with_valid_data(hass: HomeAssistant):
    """Test _process_detail_results with a valid full_detail_response dictionary."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn1_valid"
    # Create a deep copy to avoid side effects if MOCK_API_DETAILS_DATA_WWN1 is global
    # and could be modified in other tests (not the case here, but good practice).
    # import copy; valid_input = copy.deepcopy(MOCK_API_DETAILS_DATA_WWN1)
    valid_input = MOCK_API_DETAILS_DATA_WWN1
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, valid_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == valid_input["data"][ATTR_DEVICE]
    assert (
        target_data_dict[KEY_DETAILS_SMART_LATEST]
        == valid_input["data"][ATTR_SMART_RESULTS][0]
    )
    assert target_data_dict[KEY_DETAILS_METADATA] == valid_input[ATTR_METADATA]
    print(f"SUCCESS: {test_process_detail_results_with_valid_data.__name__} passed!")


def test_process_detail_results_with_exception_input(hass: HomeAssistant, caplog):
    """Test _process_detail_results when full_detail_response is an Exception."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_ex_input"
    exception_input = ValueError("Simulated error from asyncio.gather for details")
    target_data_dict = {}

    # Optional: Test if a warning is logged
    # caplog fixture from pytest captures log output
    # import logging; caplog.set_level(logging.WARNING) # Ensure WARNINGS are captured

    coordinator._process_detail_results(wwn_key, exception_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == {}
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}
    assert target_data_dict[KEY_DETAILS_METADATA] == {}
    # Optional: Check the log output
    # assert f"Failed to fetch details for disk {wwn_key}" in caplog.text
    # assert str(exception_input) in caplog.text
    print(
        f"SUCCESS: {test_process_detail_results_with_exception_input.__name__} passed!"
    )


def test_process_detail_results_missing_data_key_in_payload(hass: HomeAssistant):
    """Test _process_detail_results with missing 'data' key in the response payload."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_no_data_key"
    faulty_input = {  # 'data' key is missing at the top level
        "success": True,
        # "data": { ... } # MISSING!
        ATTR_METADATA: {"1": {"display_name": "Test Attr"}},
    }
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, faulty_input, target_data_dict)

    # Expects empty dicts because 'data' is missing to extract 'device' and 'smart_results'
    assert target_data_dict[KEY_DETAILS_DEVICE] == {}
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}
    # Metadata is at the top level and should still be extracted
    assert target_data_dict[KEY_DETAILS_METADATA] == faulty_input[ATTR_METADATA]
    print(
        f"SUCCESS: {test_process_detail_results_missing_data_key_in_payload.__name__} passed!"
    )


def test_process_detail_results_missing_smart_results_in_data(hass: HomeAssistant):
    """Test _process_detail_results with missing 'smart_results' within the 'data' payload."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_no_smart_results"
    faulty_input = {
        "success": True,
        "data": {
            ATTR_DEVICE: {"model_name": "TestDiskWithNoSmart"},
            # ATTR_SMART_RESULTS is missing here in the 'data' object!
        },
        ATTR_METADATA: {"1": {"display_name": "Test Attr"}},
    }
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, faulty_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == faulty_input["data"][ATTR_DEVICE]
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}  # Should be empty
    assert target_data_dict[KEY_DETAILS_METADATA] == faulty_input[ATTR_METADATA]
    print(
        f"SUCCESS: {test_process_detail_results_missing_smart_results_in_data.__name__} passed!"
    )


def test_process_detail_results_empty_smart_results_list(hass: HomeAssistant):
    """Test _process_detail_results with an empty 'smart_results' list."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_empty_smart_list"
    faulty_input = {
        "success": True,
        "data": {
            ATTR_DEVICE: {"model_name": "TestDiskEmptySmart"},
            ATTR_SMART_RESULTS: [],  # Empty list!
        },
        ATTR_METADATA: {"1": {"display_name": "Test Attr"}},
    }
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, faulty_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == faulty_input["data"][ATTR_DEVICE]
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}  # Should be empty
    assert target_data_dict[KEY_DETAILS_METADATA] == faulty_input[ATTR_METADATA]
    print(
        f"SUCCESS: {test_process_detail_results_empty_smart_results_list.__name__} passed!"
    )


def test_process_detail_results_missing_metadata_key_in_payload(hass: HomeAssistant):
    """Test _process_detail_results with missing 'metadata' key in the response payload."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_no_metadata"
    faulty_input = {
        "success": True,
        "data": {
            ATTR_DEVICE: {"model_name": "TestDiskNoMetadata"},
            ATTR_SMART_RESULTS: [
                {"attrs": {}, "Status": 0}  # Valid, but empty smart results
            ],
        },
        # ATTR_METADATA is missing!
    }
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, faulty_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == faulty_input["data"][ATTR_DEVICE]
    assert (
        target_data_dict[KEY_DETAILS_SMART_LATEST]
        == faulty_input["data"][ATTR_SMART_RESULTS][0]
    )
    assert target_data_dict[KEY_DETAILS_METADATA] == {}  # Should be empty
    print(
        f"SUCCESS: {test_process_detail_results_missing_metadata_key_in_payload.__name__} passed!"
    )
