# tests/test_options_flow.py (or at the end of test_config_flow.py)

import pytest
from unittest.mock import patch  # AsyncMock not strictly necessary here

from homeassistant.data_entry_flow import InvalidData  # Import the exception

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant import data_entry_flow

from custom_components.scrutiny.const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Data for the initial ConfigEntry
INITIAL_CONFIG_DATA = {
    CONF_HOST: "scrutiny.options.local",
    CONF_PORT: 8080,
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES,  # Start with default
}


@pytest.mark.asyncio
async def test_options_flow_init_and_save(
    hass: HomeAssistant,
    enable_custom_integrations: None,  # Important for the OptionsFlow Handler to be found
):
    """Test initializing the options flow and saving a new scan interval."""
    # 1. Create and register a ConfigEntry for which options should be changed
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=INITIAL_CONFIG_DATA,
        title="Scrutiny Options Test",
        # Options are initially empty or have defaults
        options={},
    )
    config_entry.add_to_hass(hass)

    # 2. Start the Options Flow for this ConfigEntry
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    await hass.async_block_till_done()

    # 3. Check if the options form is displayed correctly
    assert result["type"] == data_entry_flow.FlowResultType.FORM  # type: ignore
    assert result["step_id"] == "init"  # type: ignore

    # 4. Simulate user input in the Options Flow
    new_scan_interval = 15
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SCAN_INTERVAL: new_scan_interval},
    )
    await hass.async_block_till_done()

    # 5. Check if the flow was successful and created/saved the options
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY  # type: ignore
    # The 'title' is often empty for Options Flows; data is stored in 'data'
    assert result2["data"] == {CONF_SCAN_INTERVAL: new_scan_interval}  # type: ignore

    # 6. Überprüfe, ob die Optionen im ConfigEntry aktualisiert wurden
    assert config_entry.options == {CONF_SCAN_INTERVAL: new_scan_interval}

    print(f"SUCCESS: {test_options_flow_init_and_save.__name__} passed!")


@pytest.mark.asyncio
async def test_options_flow_invalid_input(
    hass: HomeAssistant,
    enable_custom_integrations: None,
):
    """Test options flow raises InvalidData for invalid scan interval input."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data=INITIAL_CONFIG_DATA,
        options={},  # Start with empty options
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    await hass.async_block_till_done()

    # Simulate invalid input
    invalid_scan_interval = 0

    # Expect InvalidData to be thrown, as schema validation
    # by the Home Assistant OptionsFlowManager fails.
    with pytest.raises(InvalidData) as excinfo:
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_SCAN_INTERVAL: invalid_scan_interval},
        )

    # Check the details of the InvalidData exception
    assert excinfo.value.schema_errors is not None
    assert CONF_SCAN_INTERVAL in excinfo.value.schema_errors
    # The error message comes from your 'msg' in the voluptuous schema
    assert (
        "Scan interval must be at least 1 minute"
        in excinfo.value.schema_errors[CONF_SCAN_INTERVAL]
    )
    # The original options should not have been changed, as the flow aborted
    assert config_entry.options == {}

    print(f"SUCCESS: {test_options_flow_invalid_input.__name__} passed!")
