"""DataUpdateCoordinator for the Scrutiny Home Assistant integration."""

import asyncio
from datetime import timedelta
from logging import Logger
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiError,
    ScrutinyApiResponseError,
)
from .const import (
    ATTR_ARCHIVED,
    ATTR_DEVICE,
    ATTR_METADATA,
    ATTR_SMART,
    ATTR_SMART_RESULTS,
    CONF_SHOW_ARCHIVED,
    DEFAULT_SHOW_ARCHIVED,
    KEY_DETAILS_METADATA,
    KEY_DETAILS_SMART_LATEST,
    KEY_SUMMARY_DEVICE,
    KEY_SUMMARY_SMART,
    LOGGER,
)


class ScrutinyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """
    Manages fetching and coordinating Scrutiny data updates.

    Polls the Scrutiny API on a configurable interval, aggregating summary and
    detail data for each disk.  The coordinator's ``data`` attribute is a dict
    keyed by the Scrutiny disk identifier (a UUIDv5 on Scrutiny ≥ 0.9.0, or the
    WWN hex string on older releases); each value is itself a dict using the
    ``KEY_*`` constants from ``const.py``.

    After each successful poll that returns at least one disk, any HA device
    entries for identifiers no longer present in the API response are removed,
    keeping the HA device list in sync with Scrutiny automatically.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: Logger,
        config_entry: ConfigEntry,
        name: str,
        api_client: ScrutinyApiClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize the data update coordinator."""
        self.api_client = api_client
        super().__init__(
            hass,
            logger,
            config_entry=config_entry,
            name=name,
            update_interval=update_interval,
        )

    def _process_detail_results(
        self,
        disk_id: str,
        full_detail_response: Any,
        target_data_dict: dict[str, Any],
    ) -> None:
        """
        Process the result of a single disk's detail fetch.

        Populates *target_data_dict* with ``KEY_DETAILS_SMART_LATEST`` and
        ``KEY_DETAILS_METADATA`` from *full_detail_response*.  If the fetch
        raised an exception (captured by ``asyncio.gather(return_exceptions=True)``),
        those keys are set to empty dicts so sensors degrade gracefully.
        """
        if isinstance(full_detail_response, Exception):
            self.logger.warning(
                "Failed to fetch details for disk %s: %s — summary data will be used.",
                disk_id,
                full_detail_response,
            )
            target_data_dict[KEY_DETAILS_SMART_LATEST] = {}
            target_data_dict[KEY_DETAILS_METADATA] = {}
            return

        if not isinstance(full_detail_response, dict):
            self.logger.error(
                "Unexpected response type %s for disk %s details.",
                type(full_detail_response).__name__,
                disk_id,
            )
            target_data_dict[KEY_DETAILS_SMART_LATEST] = {}
            target_data_dict[KEY_DETAILS_METADATA] = {}
            return

        # Response shape: {"data": {"device": …, "smart_results": […]}, "metadata": {…}}
        payload = full_detail_response.get("data", {})
        LOGGER.debug("Details for disk %s: %s", disk_id, str(payload)[:300])

        smart_results: list[Any] = payload.get(ATTR_SMART_RESULTS, [])
        target_data_dict[KEY_DETAILS_SMART_LATEST] = (
            smart_results[0]
            if smart_results and isinstance(smart_results, list)
            else {}
        )
        if not target_data_dict[KEY_DETAILS_SMART_LATEST]:
            self.logger.debug("No SMART results in details for disk %s.", disk_id)

        target_data_dict[KEY_DETAILS_METADATA] = full_detail_response.get(
            ATTR_METADATA, {}
        )

    def _cleanup_stale_devices(self, current_disk_ids: set[str]) -> None:
        """
        Remove HA device entries whose disk identifier is no longer returned by the API.

        Only called after a successful poll that returned at least one disk,
        so a temporary API failure can never wipe all devices.
        """
        device_registry = dr.async_get(self.hass)

        for device_entry in dr.async_entries_for_config_entry(
            device_registry, self.config_entry.entry_id
        ):
            # Skip the hub device (identified by the entry_id, not a disk UUID).
            entry_identifiers = {ident[1] for ident in device_entry.identifiers}
            if self.config_entry.entry_id in entry_identifiers:
                continue

            if not entry_identifiers.intersection(current_disk_ids):
                self.logger.info(
                    "Removing stale Scrutiny device %s"
                    " (disk identifier no longer in API response).",
                    device_entry.name,
                )
                device_registry.async_remove_device(device_entry.id)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """
        Fetch summary and detailed disk data from the Scrutiny API.

        Called periodically by the base ``DataUpdateCoordinator``.  Fetches the
        summary for all disks first, then concurrently fetches per-disk details.
        Archived disks are filtered out when the option is disabled.  After a
        successful poll with at least one disk, stale HA devices are removed.

        Raises:
            UpdateFailed: On any API or unexpected error.

        """
        show_archived: bool = (
            self.config_entry.options.get(CONF_SHOW_ARCHIVED, DEFAULT_SHOW_ARCHIVED)
            if self.config_entry is not None
            else DEFAULT_SHOW_ARCHIVED
        )

        self.logger.debug("Starting Scrutiny data update cycle.")
        aggregated: dict[str, dict[str, Any]] = {}
        summary_data: dict[str, Any] = {}

        try:
            summary_data = await self.api_client.async_get_summary()
            if not isinstance(summary_data, dict):
                raise ScrutinyApiResponseError(
                    "Summary data from API was not a dictionary."
                )

            # Filter archived disks based on user preference.
            filtered_summary: dict[str, Any] = {}
            for disk_id, disk_info in summary_data.items():
                device_data = disk_info.get(ATTR_DEVICE, {})
                is_archived = device_data.get(ATTR_ARCHIVED, False)
                if is_archived and not show_archived:
                    self.logger.debug(
                        "Skipping archived disk %s (show_archived disabled).",
                        disk_id,
                    )
                    continue
                filtered_summary[disk_id] = disk_info

            self.logger.debug(
                "Fetched summary: %d disk(s) total, %d after archive filter.",
                len(summary_data),
                len(filtered_summary),
            )

            disk_id_order: list[str] = list(filtered_summary.keys())
            for disk_id, disk_info in filtered_summary.items():
                aggregated[disk_id] = {
                    KEY_SUMMARY_DEVICE: disk_info.get(ATTR_DEVICE, {}),
                    KEY_SUMMARY_SMART: disk_info.get(ATTR_SMART, {}),
                    KEY_DETAILS_SMART_LATEST: {},
                    KEY_DETAILS_METADATA: {},
                }

            if disk_id_order:
                # Limit concurrent detail requests to avoid overwhelming Scrutiny
                # when monitoring many disks. A semaphore allows up to 5 requests
                # at once; each new request starts as soon as a slot frees rather
                # than waiting for a whole batch to complete.
                semaphore = asyncio.Semaphore(5)

                async def _fetch_with_limit(disk_id: str) -> Any:
                    async with semaphore:
                        return await self.api_client.async_get_device_details(disk_id)

                detail_results = await asyncio.gather(
                    *(_fetch_with_limit(d) for d in disk_id_order),
                    return_exceptions=True,
                )
                for disk_id, result in zip(disk_id_order, detail_results, strict=False):
                    self._process_detail_results(disk_id, result, aggregated[disk_id])
            else:
                self.logger.debug("No disks to fetch details for after filtering.")

        except ScrutinyApiConnectionError as err:
            raise UpdateFailed(f"Connection error during data update: {err}") from err
        except ScrutinyApiError as err:
            raise UpdateFailed(f"API error during data update: {err}") from err
        except UpdateFailed:
            raise
        except Exception as err:
            self.logger.exception("Unexpected error during Scrutiny data update cycle")
            raise UpdateFailed(f"Unexpected error during data update: {err}") from err

        self.logger.debug("Data update complete. Disk IDs: %s", list(aggregated.keys()))

        # Only clean up when the API returned at least one disk — prevents
        # accidental wipeout if the server returns an empty response.
        if self.config_entry is not None and len(summary_data) > 0:
            self._cleanup_stale_devices(set(filtered_summary.keys()))

        return aggregated
