"""
Custom integration to integrate Scrutiny with Home Assistant.

Polls a Scrutiny API endpoint to retrieve disk health information and
exposes it as diagnostic sensor entities in Home Assistant.
"""

import logging
from datetime import timedelta
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType

from .api import ScrutinyApiClient
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    NAME,
    PLATFORMS,
    VERSION,
)
from .coordinator import ScrutinyDataUpdateCoordinator

# Typed alias so platforms can annotate their config entry argument precisely.
type ScrutinyConfigEntry = ConfigEntry[ScrutinyDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ScrutinyConfigEntry) -> bool:
    """Set up Scrutiny from a config entry."""
    url: str = entry.data[CONF_URL]
    verify_ssl: bool = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    scan_interval_minutes: int = entry.options.get(
        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
    )

    # Parse the URL for display purposes (device name, configuration_url).
    parsed = urlparse(url)
    display_host = parsed.hostname or url

    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=logging.getLogger(__name__),
        config_entry=entry,
        name=f"Scrutiny ({display_host})",
        api_client=ScrutinyApiClient(
            base_url=url,
            session=async_get_clientsession(hass, verify_ssl=verify_ssl),
        ),
        update_interval=timedelta(minutes=scan_interval_minutes),
    )

    # Fetch initial data; raises ConfigEntryNotReady on failure so HA retries.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Register a hub device linking to the Scrutiny web UI via configuration_url.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        entry_type=DeviceEntryType.SERVICE,
        name=f"{NAME} ({display_host})",
        manufacturer=NAME,
        model="Scrutiny Integration Hub",
        sw_version=VERSION,
        configuration_url=url,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when the user changes options (e.g. scan interval, entity level).
    entry.async_on_unload(entry.add_update_listener(_async_options_update_listener))

    return True


async def _async_options_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the integration when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ScrutinyConfigEntry) -> bool:
    """Unload a config entry and its associated platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ScrutinyConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """
    Allow users to remove a disk device from the UI.

    Returns True so HA removes the device from the registry.  The coordinator
    will naturally stop creating entities for this disk on the next refresh,
    so no additional cleanup is required here.
    """
    return True
