"""
Custom integration to integrate Scrutiny with Home Assistant.

This integration polls a Scrutiny API endpoint to retrieve disk health
information and presents it as sensors in Home Assistant.
"""

from __future__ import (
    annotations,
)  # Ensures compatibility for type hints, e.g. ScrutinyConfigEntry

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import (
    device_registry as dr,
)  # Import device_registry for device creation
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_HOST,  # Key for the Scrutiny server host
    CONF_PORT,  # Key for the Scrutiny server port
    CONF_SCAN_INTERVAL,  # Key for the polling interval for data updates
    DEFAULT_SCAN_INTERVAL_MINUTES,  # Default polling interval in minutes
    DOMAIN,
    LOGGER,
    NAME,
    PLATFORMS,
    VERSION,
)

# Conditional import for type checking, avoids circular imports at runtime.
if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


# Import ScrutinyApiClient for interacting with the Scrutiny API.
from .api import ScrutinyApiClient

# Import constants used by the integration.
# Import the data update coordinator.
from .coordinator import ScrutinyDataUpdateCoordinator

# Type alias for the ConfigEntry specific to this integration.
# It's annotated with the type of runtime_data it will hold (our coordinator).
# This improves type safety and autocompletion in the rest of the integration.
type ScrutinyConfigEntry = ConfigEntry[ScrutinyDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ScrutinyConfigEntry) -> bool:
    """
    Set up Scrutiny from a config entry.

    This function is called by Home Assistant when a config entry for this
    integration needs to be set up (e.g., after a successful config flow or
    on Home Assistant startup for an existing entry).

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being set up. It contains user-provided configuration
               (host, port) and will store the coordinator in its runtime_data.

    Returns:
        True if the setup was successful, False otherwise.
        If False is returned or an exception is raised, Home Assistant will
        attempt to retry the setup later.

    """
    # Retrieve host and port from the config entry's data.
    # This data was stored by the config flow (config_flow.py).
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    scan_interval_minutes = entry.options.get(  # NEU: Zuerst Optionen prüfen
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES),
    )
    update_interval = timedelta(minutes=scan_interval_minutes)

    # Get the shared aiohttp client session from Home Assistant.
    # This is the recommended way to make HTTP requests in integrations
    # as it allows Home Assistant to manage the session's lifecycle.
    session = async_get_clientsession(hass)

    # Create an instance of our API client, passing the session and connection details.
    api_client = ScrutinyApiClient(host=host, port=port, session=session)

    # Create an instance of our data update coordinator.
    # The coordinator is responsible for fetching data from the Scrutiny API
    # at regular intervals (defined by DEFAULT_SCAN_INTERVAL) and notifying
    # subscribed entities (sensors) of updates.
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,  # Pass the integration-specific logger.
        name=f"Scrutiny ({host}:{port})",  # A descriptive name for log and diagnostics.
        api_client=api_client,  # Pass the API client to the coordinator.
        update_interval=update_interval,  # Use the defined scan interval.
    )

    # Perform the first refresh of the coordinator's data.
    # This serves two purposes:
    # 1. It populates the coordinator with initial data before entities are set up.
    # 2. It allows for immediate feedback if the API is unreachable or returns an error
    #    during setup. If this fails (e.g., raises UpdateFailed), Home Assistant
    #    will handle it by retrying the setup of this config entry.
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator instance in the config entry's runtime_data.
    # This makes the coordinator accessible to platforms (like sensor.py)
    # when they are being set up. Home Assistant manages the lifecycle of runtime_data.
    entry.runtime_data = coordinator

    # Create a "hub" device for the integration.
    # This device can act as a parent for the actual disk devices.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={
            (DOMAIN, entry.entry_id)
        },  # Unique identifier for this hub device.
        name=f"{NAME} ({entry.data[CONF_HOST]})",  # User-friendly name for the hub.
        manufacturer=NAME,  # Manufacturer, typically the integration name.
        model="Scrutiny Integration Hub",  # Model of this "device".
        sw_version=VERSION,  # Software version of the integration.
    )

    # Forward the setup of this config entry to the platforms defined in PLATFORMS.
    # For each platform string in PLATFORMS (e.g., "sensor"), Home Assistant will
    # call the async_setup_entry function in the corresponding platform file
    # (e.g., sensor.py), passing this config entry.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_options_update_listener))

    # Set up an update listener. This listener will be called if the config entry
    # is updated (e.g., through an options flow, though not implemented in this version)
    # The async_reload_entry function will handle reloading the integration.
    entry.add_update_listener(async_reload_entry)

    # Return True to indicate successful setup.
    return True


async def async_options_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ScrutinyConfigEntry) -> bool:
    """
    Unload a config entry.

    This function is called by Home Assistant when a config entry for this
    integration needs to be removed or reloaded. It should clean up any
    resources used by the integration for this entry, such as unregistering
    listeners or stopping background tasks.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being unloaded.

    Returns:
        True if the unload was successful, False otherwise.

    """
    # Unload the platforms associated with this config entry.
    # This will call the async_unload_entry function in each platform file
    # (e.g., sensor.py), allowing them to clean up their entities.
    # The coordinator and API client (if they had cleanup) would also be handled here,
    # but typically, releasing references is sufficient for Python's garbage collection.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Reload a config entry.

    This is called when a config entry needs to be reloaded, for instance,
    after its options have been changed (if an options flow were implemented).
    It typically involves unloading and then setting up the entry again.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to reload.

    """
    # Home Assistant provides a helper to reload an entry, which internally
    # calls async_unload_entry and then async_setup_entry for this entry.
    await hass.config_entries.async_reload(entry.entry_id)
