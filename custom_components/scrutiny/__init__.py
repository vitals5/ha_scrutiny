"""Custom integration to integrate Scrutiny with Home Assistant."""

from __future__ import annotations  # Ensure this is at the very top

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
)  # Platform wird in const.py definiert
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ScrutinyApiClient,
)  # Import API client and exceptions
from .const import DEFAULT_SCAN_INTERVAL, LOGGER, PLATFORMS  # Import PLATFORMS
from .coordinator import (
    ScrutinyDataUpdateCoordinator,
)  # Assuming this will be our coordinator class

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Define a type alias for our ConfigEntry that includes runtime_data for the coordinator
# This helps with type hinting throughout the integration.
# The actual ScrutinyDataUpdateCoordinator type will be used once it's defined.
type ScrutinyConfigEntry = ConfigEntry[ScrutinyDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ScrutinyConfigEntry) -> bool:
    """Set up Scrutiny from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    # Create API client
    session = async_get_clientsession(hass)
    api_client = ScrutinyApiClient(host=host, port=port, session=session)

    # Create DataUpdateCoordinator
    # The ScrutinyDataUpdateCoordinator class needs to be defined in coordinator.py
    # It will take the api_client and define its own _async_update_data method.
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,  # Use our domain-specific logger
        name=f"Scrutiny Coordinator ({host}:{port})",  # Informative name
        api_client=api_client,  # Pass the API client to the coordinator
        update_interval=DEFAULT_SCAN_INTERVAL,  # Use defined scan interval
    )

    # Perform the first refresh to catch immediate errors and populate data
    # This will call coordinator._async_update_data()
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator in hass.data for platforms to access
    # The blueprint had hass.data.setdefault(DOMAIN, {}), which is good.
    # We'll use the entry specific storage.
    # entry.runtime_data is the modern way to store coordinator.
    entry.runtime_data = coordinator

    # Forward the setup to the defined platforms (e.g., sensor)
    # PLATFORMS should be defined in const.py, e.g., PLATFORMS = [Platform.SENSOR]
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Add an update listener for options flow (if we add one later) or other changes
    entry.add_update_listener(async_reload_entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ScrutinyConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms first
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    # This will call async_unload_entry and then async_setup_entry
    await hass.config_entries.async_reload(entry.entry_id)
