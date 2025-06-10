import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.config_entries import ConfigEntryState, ConfigEntry
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession,  # For the patch
)

# Import the functions and constants to be tested
from custom_components.scrutiny import async_setup_entry, async_unload_entry
from custom_components.scrutiny.const import (
    DOMAIN,
    CONF_PORT as SCRUTINY_CONF_PORT,  # Alias for clarity if const.py also uses CONF_PORT
    DEFAULT_PORT,
    PLATFORMS,
)

# Import the classes we want to mock
from custom_components.scrutiny.api import ScrutinyApiClient
from custom_components.scrutiny.coordinator import ScrutinyDataUpdateCoordinator

# Helpers from pytest-homeassistant-custom-component
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Testdaten für einen ConfigEntry
MOCK_CONFIG_DATA = {
    CONF_HOST: "test-scrutiny.local",
    SCRUTINY_CONF_PORT: 8088,  # Verwende den Port-Konstanten aus deiner Integration
    # Use the port constant from your integration
}


@pytest.mark.asyncio
async def test_async_setup_entry_success(hass: HomeAssistant):
    """Test successful setup of the integration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        title="Test Scrutiny Instance",
    )
    entry.add_to_hass(hass)

    mock_session = MagicMock()
    with (
        patch(
            "custom_components.scrutiny.async_get_clientsession",
            return_value=mock_session,
        ) as mock_get_session,
        patch(
            "custom_components.scrutiny.ScrutinyApiClient", autospec=True
        ) as mock_api_client_class,
        patch(
            "custom_components.scrutiny.ScrutinyDataUpdateCoordinator", autospec=True
        ) as mock_coordinator_class,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            return_value=True,
        ) as mock_forward_setup,
        patch("homeassistant.helpers.device_registry.async_get") as mock_async_get_dr,
    ):
        mock_dr = MagicMock()
        mock_async_get_dr.return_value = mock_dr

        mock_coordinator_instance = mock_coordinator_class.return_value
        mock_coordinator_instance.async_config_entry_first_refresh = AsyncMock(
            return_value=None
        )
        mock_coordinator_instance.data = {"some_wwn": {}}

        # Führe die zu testende Funktion aus
        # Execute the function to be tested
        setup_result = await async_setup_entry(hass, entry)
        assert setup_result is True  # Ensure True is returned
        await hass.async_block_till_done()

    # Check calls and initializations
    mock_get_session.assert_called_once_with(hass)
    mock_api_client_class.assert_called_once_with(
        host=MOCK_CONFIG_DATA[CONF_HOST],
        port=MOCK_CONFIG_DATA[SCRUTINY_CONF_PORT],
        session=mock_session,
    )
    mock_coordinator_class.assert_called_once()
    coordinator_args = mock_coordinator_class.call_args[1]
    assert coordinator_args["hass"] == hass
    assert coordinator_args["api_client"] == mock_api_client_class.return_value

    mock_coordinator_instance.async_config_entry_first_refresh.assert_called_once()
    assert entry.runtime_data == mock_coordinator_instance

    mock_async_get_dr.assert_called_once_with(hass)
    mock_dr.async_get_or_create.assert_called_once()

    mock_forward_setup.assert_called_once_with(entry, PLATFORMS)

    # The ConfigEntryState.LOADED is set by Home Assistant after successful setup
    # and platform forwarding, so we don't assert it directly here.

    print(f"SUCCESS: {test_async_setup_entry_success.__name__} passed!")


@pytest.mark.asyncio
async def test_async_setup_entry_first_refresh_fails(hass: HomeAssistant):
    """Test setup fails if coordinator.async_config_entry_first_refresh raises UpdateFailed."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
    entry.add_to_hass(hass)

    mock_session = MagicMock()
    with (
        patch(
            "custom_components.scrutiny.async_get_clientsession",
            return_value=mock_session,
        ),
        patch("custom_components.scrutiny.ScrutinyApiClient", autospec=True),
        patch(
            "custom_components.scrutiny.ScrutinyDataUpdateCoordinator", autospec=True
        ) as mock_coordinator_class,
    ):
        mock_coordinator_instance = mock_coordinator_class.return_value
        mock_coordinator_instance.async_config_entry_first_refresh = AsyncMock(
            side_effect=UpdateFailed("Simulated first refresh failure")
        )

        with pytest.raises(UpdateFailed) as excinfo:
            await async_setup_entry(hass, entry)

        assert "Simulated first refresh failure" in str(excinfo.value)

        # Ensure runtime_data was not set (or not with the coordinator)
        # entry.runtime_data is set in __init__.py *after* first_refresh.
        # If first_refresh fails, runtime_data should not contain the coordinator.
        # It could be None or not exist at all, depending on MockConfigEntry behavior.
        assert (
            not hasattr(entry, "runtime_data")
            or entry.runtime_data is None
            or entry.runtime_data != mock_coordinator_instance
        )  # Ensure it's not the coordinator

        # ConfigEntryState.SETUP_ERROR is set by HA if async_setup_entry raises an exception.

    print(f"SUCCESS: {test_async_setup_entry_first_refresh_fails.__name__} passed!")


@pytest.mark.asyncio
async def test_async_unload_entry_success(hass: HomeAssistant):
    """Test successful unload of the integration."""
    # Create a MockConfigEntry
    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_CONFIG_DATA, title="Test Scrutiny to Unload"
    )
    # It's not strictly necessary to add it to hass for this test,
    # as async_unload_entry receives the entry directly as an argument.
    # But it doesn't hurt either, in case other parts of the test framework expect it.
    entry.add_to_hass(hass)

    # Mock hass.config_entries.async_unload_platforms
    # This method is on the ConfigEntries instance, not directly on hass.
    # The path for patching is therefore important.
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        new_callable=AsyncMock,  # As it's an async method
        return_value=True,  # Simulate successful unloading of platforms
    ) as mock_unload_platforms:
        # Execute the function to be tested
        unload_result = await async_unload_entry(hass, entry)
        assert unload_result is True

    # Check if the method was called with the correct arguments
    mock_unload_platforms.assert_called_once_with(entry, PLATFORMS)

    # Optional: If your async_unload_entry explicitly clears runtime_data,
    # you could check that here. Typically, this is not the task
    # of async_unload_entry itself, but happens as part of the HA process.
    # if hasattr(entry, "runtime_data"):
    #     assert entry.runtime_data is None

    # Checking entry.state (e.g., for NOT_LOADED) is difficult here,
    # as MockConfigEntry doesn't automatically update its status.
    # The most important thing is that the function returns True and unloads the platforms.

    print(f"SUCCESS: {test_async_unload_entry_success.__name__} passed!")
