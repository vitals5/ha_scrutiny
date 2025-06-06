"""DataUpdateCoordinator for the Scrutiny Home Assistant integration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, NoReturn

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiError,
    ScrutinyApiResponseError,
)
from .const import (
    # API response field names (used when parsing API responses)
    ATTR_DEVICE,  # Actual key in Scrutiny's API response for device objects
    ATTR_METADATA,  # Actual key in Scrutiny's API details response
    ATTR_SMART,  # Actual key in Scrutiny's API summary response for smart objects
    ATTR_SMART_RESULTS,  # Actual key in Scrutiny's API details response
    KEY_DETAILS_DEVICE,
    KEY_DETAILS_METADATA,
    KEY_DETAILS_SMART_LATEST,
    # Keys for navigating the aggregated data structure (used when building it here)
    KEY_SUMMARY_DEVICE,
    KEY_SUMMARY_SMART,
    # General
    LOGGER,
)

if TYPE_CHECKING:
    from datetime import timedelta
    from logging import Logger

    from homeassistant.core import HomeAssistant


def _raise_update_failed(message: str, error: Exception) -> NoReturn:
    """Construct and consistently raise an UpdateFailed exception."""
    final_message = f"{message}: {error!s}"
    raise UpdateFailed(final_message) from error


def _raise_scrutiny_api_error_from_coordinator(
    message: str, *, is_response_error: bool = True
) -> NoReturn:
    """Raise a ScrutinyApi(Response)Error from coordinator logic."""
    if is_response_error:
        raise ScrutinyApiResponseError(message)
    raise ScrutinyApiError(message)


class ScrutinyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Manages fetching and coordinating Scrutiny data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: Logger,
        name: str,
        api_client: ScrutinyApiClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize the data update coordinator."""
        self.api_client = api_client
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        self.aggregated_disk_data: dict[str, dict[str, Any]] = {}

    def _process_detail_results(
        self,
        wwn_key: str,
        # 'full_detail_response' ist jetzt das gesamte Objekt:
        # {"data": {"device": ..., "smart_results": ...},
        # "metadata": ..., "success": true}
        full_detail_response: Any,
        target_data_dict: dict[str, Any],
    ) -> None:
        """Process the result of a single disk's detail fetch operation."""
        if isinstance(full_detail_response, Exception):
            self.logger.warning(
                "Failed to fetch details for disk %s: %s. Summary data will be used.",
                wwn_key,
                full_detail_response,
            )
            target_data_dict[KEY_DETAILS_DEVICE] = {}
            target_data_dict[KEY_DETAILS_SMART_LATEST] = {}
            target_data_dict[KEY_DETAILS_METADATA] = {}
        elif isinstance(full_detail_response, dict):
            actual_payload = full_detail_response.get("data", {})

            LOGGER.debug(
                """COORDINATOR _process_detail_results
                  (WWN: %s): Full detail response: %s""",
                wwn_key,
                str(full_detail_response)[:500],
            )
            LOGGER.debug(
                """COORDINATOR _process_detail_results (WWN: %s):
                Extracted 'actual_payload' (for device/smart_results): %s""",
                wwn_key,
                str(actual_payload)[:500],
            )

            target_data_dict[KEY_DETAILS_DEVICE] = actual_payload.get(ATTR_DEVICE, {})

            smart_results_list = actual_payload.get(ATTR_SMART_RESULTS, [])
            if (
                smart_results_list
                and isinstance(smart_results_list, list)
                and smart_results_list[0]
            ):
                target_data_dict[KEY_DETAILS_SMART_LATEST] = smart_results_list[0]
            else:
                target_data_dict[KEY_DETAILS_SMART_LATEST] = {}
                self.logger.debug(
                    "No smart_results found or empty in details for disk %s.", wwn_key
                )

            metadata_content = full_detail_response.get(ATTR_METADATA, {})
            target_data_dict[KEY_DETAILS_METADATA] = metadata_content

            LOGGER.debug(
                "COORDINATOR _process_detail_results (WWN: %s): Stored METADATA: %s",
                wwn_key,
                str(metadata_content)[:500],
            )

        else:
            self.logger.error(
                "Unexpected result type (%s) for disk %s full_detail_response.",
                type(full_detail_response).__name__,
                wwn_key,
            )
            target_data_dict[KEY_DETAILS_DEVICE] = {}
            target_data_dict[KEY_DETAILS_SMART_LATEST] = {}
            target_data_dict[KEY_DETAILS_METADATA] = {}  # Wichtig

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch the latest summary and detailed disk data from the Scrutiny API."""
        self.logger.debug("Starting Scrutiny data update cycle.")
        current_run_aggregated_data: dict[str, dict[str, Any]] = {}

        try:
            summary_data = await self.api_client.async_get_summary()
            if not isinstance(summary_data, dict):
                _raise_scrutiny_api_error_from_coordinator(
                    "Summary data from API was not a dictionary."
                )

            self.logger.debug(
                "Successfully fetched summary data for %d disk(s).", len(summary_data)
            )

            detail_tasks = []
            wwn_order = []
            for wwn, disk_summary_info in summary_data.items():
                wwn_order.append(wwn)
                # Initialize with KEY_.. constants for our internal aggregated structure
                current_run_aggregated_data[wwn] = {
                    KEY_SUMMARY_DEVICE: disk_summary_info.get(
                        ATTR_DEVICE, {}
                    ),  # API key is "device"
                    KEY_SUMMARY_SMART: disk_summary_info.get(
                        ATTR_SMART, {}
                    ),  # API key is "smart"
                    KEY_DETAILS_DEVICE: {},  # filled by _process_detail_results
                    KEY_DETAILS_SMART_LATEST: {},  # Placeholder
                    KEY_DETAILS_METADATA: {},  # Placeholder
                }
                detail_tasks.append(self.api_client.async_get_device_details(wwn))

            if detail_tasks:
                self.logger.debug("Fetching details for %d disk(s).", len(detail_tasks))
                detail_results = await asyncio.gather(
                    *detail_tasks, return_exceptions=True
                )
                for i, wwn_key in enumerate(wwn_order):
                    self._process_detail_results(
                        wwn_key, detail_results[i], current_run_aggregated_data[wwn_key]
                    )
            else:
                self.logger.debug("No disks found in summary to fetch details for.")

        except ScrutinyApiConnectionError as err:
            _raise_update_failed(
                "Connection error during Scrutiny data update cycle", err
            )
        except ScrutinyApiError as err:
            _raise_update_failed(
                f"API error during Scrutiny data update cycle: {err!s}", err
            )
        except Exception as err:
            self.logger.exception("Unexpected error during Scrutiny data update cycle")
            _raise_update_failed(
                "An unexpected error occurred during Scrutiny data update", err
            )

        self.logger.debug(
            "Scrutiny data update cycle completed. Aggregated data keys: %s",
            list(current_run_aggregated_data.keys()),
        )
        self.aggregated_disk_data = current_run_aggregated_data
        return self.aggregated_disk_data
