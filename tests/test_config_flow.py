import pytest
from unittest.mock import patch, AsyncMock

from homeassistant.data_entry_flow import InvalidData

from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
)


from pytest_homeassistant_custom_component.common import MockConfigEntry

# Import the Config Flow Handler and constants to be tested
from custom_components.scrutiny.config_flow import ScrutinyConfigFlowHandler
from custom_components.scrutiny.const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)

# Importiere die Exceptions, die _test_connection werfen könnte (und die wir mocken)
from custom_components.scrutiny.api import (  # <--- HIER
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
    ScrutinyApiAuthError,
)

# Test data for user input
USER_INPUT_WITH_INTERVAL = {
    CONF_HOST: "scrutiny.test.local",
    CONF_PORT: 8080,
    CONF_SCAN_INTERVAL: 30,
}

# Test data for user input without explicit port
USER_INPUT_NO_PORT = {
    CONF_HOST: "scrutiny.defaultport.local",
    # CONF_PORT is omitted
}

# Test data for user input with defaults
USER_INPUT_DEFAULTS = {
    CONF_HOST: "scrutiny.defaults.local",
}


@pytest.mark.asyncio
async def test_config_flow_user_step_success(
    hass: HomeAssistant,
    enable_custom_integrations: None,
):
    """Test a successful user configuration flow with scan interval."""
    with patch(
        "custom_components.scrutiny.config_flow.ScrutinyConfigFlowHandler._test_connection",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_test_connection:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        assert result["type"] == data_entry_flow.FlowResultType.FORM  # type: ignore
        assert result["errors"] == {}  # type: ignore

        # Simulate user input WITH scan interval
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            USER_INPUT_WITH_INTERVAL,
        )
        await hass.async_block_till_done()

    # _test_connection is called only with host and port
    mock_test_connection.assert_called_once_with(
        USER_INPUT_WITH_INTERVAL[CONF_HOST], USER_INPUT_WITH_INTERVAL[CONF_PORT]
    )

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY  # type: ignore
    assert (
        result2["title"]  # type: ignore
        == f"Scrutiny ({USER_INPUT_WITH_INTERVAL[CONF_HOST]}:{USER_INPUT_WITH_INTERVAL[CONF_PORT]})"
    )

    result2_data = result2["data"]  # type: ignore
    assert isinstance(result2_data, dict)
    assert result2_data[CONF_HOST] == USER_INPUT_WITH_INTERVAL[CONF_HOST]
    assert result2_data[CONF_PORT] == USER_INPUT_WITH_INTERVAL[CONF_PORT]
    assert (
        result2_data[CONF_SCAN_INTERVAL] == USER_INPUT_WITH_INTERVAL[CONF_SCAN_INTERVAL]
    )  # NEUE PRÜFUNG

    config_entry_obj = result2["result"]  # type: ignore
    assert isinstance(config_entry_obj, config_entries.ConfigEntry)
    # Unique ID should remain unchanged (based only on host/port)
    assert (
        config_entry_obj.unique_id
        == f"{USER_INPUT_WITH_INTERVAL[CONF_HOST]}:{USER_INPUT_WITH_INTERVAL[CONF_PORT]}"
    )

    print(
        f"SUCCESS: {test_config_flow_user_step_success.__name__} (with interval) passed!"
    )


@pytest.mark.asyncio
async def test_config_flow_user_step_cannot_connect(
    hass: HomeAssistant,
    enable_custom_integrations: None,
):
    """Test config flow when _test_connection raises ScrutinyApiConnectionError."""
    # 1. Patch _test_connection to throw ScrutinyApiConnectionError
    with patch(
        "custom_components.scrutiny.config_flow.ScrutinyConfigFlowHandler._test_connection",
        new_callable=AsyncMock,
        side_effect=ScrutinyApiConnectionError("Simulated connection error"),
    ) as mock_test_connection:
        # 2. Initialize the Config Flow (first call shows the form)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        # We don't expect any errors here yet, as the form is only displayed
        assert result["type"] == data_entry_flow.FlowResultType.FORM  # type: ignore
        assert result["errors"] == {}  # type: ignore

        # 3. Simulate user input
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT_WITH_INTERVAL
        )
        await hass.async_block_till_done()

    # 4. Check if _test_connection was called
    mock_test_connection.assert_called_once_with(
        USER_INPUT_WITH_INTERVAL[CONF_HOST], USER_INPUT_WITH_INTERVAL[CONF_PORT]
    )

    # 5. Check the result: It should show the form again, but with errors
    assert result2 is not None
    assert result2["type"] == data_entry_flow.FlowResultType.FORM  # type: ignore
    assert result2["step_id"] == "user"  # type: ignore

    # Check if the correct error for "base" is displayed
    # (your config_flow.py uses "base" for generic connection errors)
    errors = result2["errors"]  # type: ignore
    assert isinstance(errors, dict)
    assert errors.get("base") == "cannot_connect"

    print(f"SUCCESS: {test_config_flow_user_step_cannot_connect.__name__} passed!")


@pytest.mark.asyncio
async def test_config_flow_user_step_already_configured(
    hass: HomeAssistant,
    enable_custom_integrations: None,
):
    """Test config flow when the Scrutiny instance is already configured."""
    # 1. Create a MockConfigEntry to simulate an existing configuration
    #    The unique_id must match the one the flow would generate.
    unique_id = (
        f"{USER_INPUT_WITH_INTERVAL[CONF_HOST]}:{USER_INPUT_WITH_INTERVAL[CONF_PORT]}"
    )
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data=USER_INPUT_WITH_INTERVAL,
        title=f"Scrutiny ({USER_INPUT_WITH_INTERVAL[CONF_HOST]}:{USER_INPUT_WITH_INTERVAL[CONF_PORT]})",  # Title is optional for the test here
    ).add_to_hass(hass)  # Add the mock entry to Home Assistant

    # 2. Patch _test_connection, as it should not be called for this test
    #    if the unique_id already exists. But we mock it for safety,
    #    in case the logic is different.
    with patch(
        "custom_components.scrutiny.config_flow.ScrutinyConfigFlowHandler._test_connection",
        new_callable=AsyncMock,
        return_value=None,  # Would signal success if called
    ) as mock_test_connection:
        # 3. Initialize the Config Flow
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # 4. Simulate user input with the same data as the existing entry
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            USER_INPUT_WITH_INTERVAL,  # Use the same input as the existing entry
        )
        await hass.async_block_till_done()

    # 5. Check if _test_connection was NOT called,
    #    as the flow should abort earlier due to the unique_id.
    mock_test_connection.assert_not_called()

    # 6. Check the result: It should be an abort with "already_configured"
    assert result2 is not None
    assert result2["type"] == data_entry_flow.FlowResultType.ABORT  # type: ignore
    assert result2["reason"] == "already_configured"  # type: ignore

    print(f"SUCCESS: {test_config_flow_user_step_already_configured.__name__} passed!")


@pytest.mark.asyncio
async def test_config_flow_user_step_defaults(  # Umbenannt für Klarheit
    hass: HomeAssistant,
    enable_custom_integrations: None,
):
    """Test config flow uses default port and default scan interval if none are provided."""
    with patch(
        "custom_components.scrutiny.config_flow.ScrutinyConfigFlowHandler._test_connection",
        new_callable=AsyncMock,
        return_value=None,
    ) as mock_test_connection:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            USER_INPUT_DEFAULTS,
        )
        await hass.async_block_till_done()

    # _test_connection is called with the default port
    mock_test_connection.assert_called_once_with(
        USER_INPUT_DEFAULTS[CONF_HOST], DEFAULT_PORT
    )

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY  # type: ignore

    expected_title = f"Scrutiny ({USER_INPUT_DEFAULTS[CONF_HOST]}:{DEFAULT_PORT})"
    assert result2["title"] == expected_title  # type: ignore

    result2_data = result2["data"]  # type: ignore
    assert isinstance(result2_data, dict)
    assert result2_data[CONF_HOST] == USER_INPUT_DEFAULTS[CONF_HOST]
    assert result2_data[CONF_PORT] == DEFAULT_PORT
    assert (
        result2_data[CONF_SCAN_INTERVAL] == DEFAULT_SCAN_INTERVAL_MINUTES
    )  # CHECK DEFAULT INTERVAL

    config_entry_obj = result2["result"]  # type: ignore
    assert isinstance(config_entry_obj, config_entries.ConfigEntry)
    assert (
        config_entry_obj.unique_id == f"{USER_INPUT_DEFAULTS[CONF_HOST]}:{DEFAULT_PORT}"
    )

    print(f"SUCCESS: {test_config_flow_user_step_defaults.__name__} passed!")


@pytest.mark.asyncio
async def test_config_flow_user_step_invalid_scan_interval(
    hass: HomeAssistant,
    enable_custom_integrations: None,
):
    """Test config flow raises InvalidData for invalid scan interval input."""
    user_input_invalid_interval = {
        CONF_HOST: "scrutiny.invalidinterval.local",
        CONF_PORT: 8080,
        CONF_SCAN_INTERVAL: 0,  # Invalid (must be >= 1)
    }

    with patch(
        "custom_components.scrutiny.config_flow.ScrutinyConfigFlowHandler._test_connection",
        new_callable=AsyncMock,  # Not called here, but patch is present
    ) as mock_test_connection:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM  # type: ignore
        assert result["errors"] == {}  # type: ignore

        # Expect InvalidData to be thrown, as schema validation
        # by the Home Assistant Flow Manager fails.
        with pytest.raises(InvalidData) as excinfo:
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input_invalid_interval,
            )

        # Optional check of exception details, if necessary.
        # The InvalidData exception often contains the original voluptuous error message.
        # excinfo.value.error_message oder excinfo.value.schema_errors
        # print(f"DEBUG: InvalidData exception: {excinfo.value}")
        # print(f"DEBUG: InvalidData schema_errors: {excinfo.value.schema_errors}")

        # The schema_errors should map the error to the correct field
        assert excinfo.value.schema_errors is not None
        assert CONF_SCAN_INTERVAL in excinfo.value.schema_errors
        # The exact error message comes from voluptuous
        assert (
            "value must be at least 1"
            in excinfo.value.schema_errors[CONF_SCAN_INTERVAL]
        )

    mock_test_connection.assert_not_called()  # As validation failed beforehand

    print(
        f"SUCCESS: {test_config_flow_user_step_invalid_scan_interval.__name__} passed!"
    )
