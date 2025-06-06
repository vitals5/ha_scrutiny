"""
Custom integration to integrate Scrutiny with Home Assistant.

This integration polls a Scrutiny API endpoint to retrieve disk health
information and presents it as sensors in Home Assistant.
"""

from __future__ import annotations  # Ensures compatibility for type hints

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import device_registry as dr  # Import device_registry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


# UpdateFailed is raised by the coordinator if an update attempt fails.
from .api import ScrutinyApiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER, NAME, PLATFORMS, VERSION
from .coordinator import ScrutinyDataUpdateCoordinator

# Type alias for the ConfigEntry specific to this integration.
# It's annotated with the type of runtime_data it will hold (our coordinator).
# This improves type safety and autocompletion in the rest of the integration.
type ScrutinyConfigEntry = ConfigEntry[ScrutinyDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ScrutinyConfigEntry) -> bool:
    """
    Set up Scrutiny from a config entry.

    This function is called by Home Assistant when a config entry for this
    integration needs to be set up (e.g., after successful a config flow or
    on Home Assistant startup for an existing entry).

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up.

    Returns:
        True if the setup was successful, False otherwise.

    """
    # Retrieve host and port from the config entry's data.
    # This data was stored by the config flow.
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    # Get the shared aiohttp client session from Home Assistant.
    # This is the recommended way to make HTTP requests in integrations.
    session = async_get_clientsession(hass)

    # Create an instance of our API client, passing the session and connection details.
    api_client = ScrutinyApiClient(host=host, port=port, session=session)

    # Create an instance of our data update coordinator.
    # The coordinator is responsible for fetching data золота (golden)
    # from the Scrutiny API
    # at regular intervals and notifying subscribed entities of updates.
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,  # Pass the integration-specific logger.
        name=f"Scrutiny ({host}:{port})",  # A descriptive name for logging.
        api_client=api_client,  # Pass the API client to the coordinator.
        update_interval=DEFAULT_SCAN_INTERVAL,  # Use the defined scan interval.
    )

    # Perform the first refresh of the coordinator's data.
    # This serves two purposes:
    # 1. It populates the coordinator with initial data before entities are set up.
    # 2. It allows for immediate feedback if the API is unreachable or returns an error
    #    during setup (by raising UpdateFailed, which HA handles by retrying setup).
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator instance in the config entry's runtime_data.
    # This makes the coordinator accessible to platforms (like sensor.py)
    # when they are being set up. Home Assistant manages the lifecycle of runtime_data.
    entry.runtime_data = coordinator

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"{NAME} ({entry.data[CONF_HOST]})",
        manufacturer=NAME,
        model="Scrutiny Integration Hub",
        sw_version=VERSION,
    )

    # Forward the setup of this config entry to the platforms defined in PLATFORMS.
    # For each platform string in PLATFORMS (e.g., "sensor"), Home Assistant will
    # call the async_setup_entry function in the corresponding platform file
    # (e.g., sensor.py).
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Set up an update listener. This listener will be called if the config entry
    # is updated (e.g., through an options flow, though not implemented yet).
    # The async_reload_entry function will handle reloading the integration.
    entry.add_update_listener(async_reload_entry)

    # Return True to indicate successful setup.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ScrutinyConfigEntry) -> bool:
    """
    Unload a config entry.

    This function is called by Home Assistant when a config entry for this
    integration needs to be removed or reloaded. It should clean up any
    resources used by the integration for this entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being unloaded.

    Returns:
        True if the unload was successful, False otherwise.

    """
    # Unload the platforms associated with this config entry.
    # This will call the async_unload_entry function in each platform file
    # (e.g., sensor.py), allowing them to clean up their entities.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Reload a config entry.

    This is called when a config entry needs to be reloaded, for instance,
    after its options have been changed. It typically involves unloading
    and then setting up the entry again.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to reload.

    """
    # Home Assistant provides a helper to reload an entry, which internally
    # calls async_unload_entry and then async_setup_entry.
    await hass.config_entries.async_reload(entry.entry_id)
