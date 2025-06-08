"""DataUpdateCoordinator for the Scrutiny Home Assistant integration."""

from __future__ import annotations

import asyncio
from typing import (
    TYPE_CHECKING,
    Any,
    NoReturn,
)  # NoReturn for functions that always raise

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,  # Base class for managing data updates
    UpdateFailed,  # Exception to signal update failures to Home Assistant
)

# Import API client and specific exceptions for error handling
from .api import (
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiError,
    ScrutinyApiResponseError,
)

# Import constants used for structuring data and logging
from .const import (
    # API response field names (used when parsing API responses from Scrutiny)
    ATTR_DEVICE,  # Key for device information object in API responses
    ATTR_METADATA,  # Key for SMART attribute metadata in API details response
    ATTR_SMART,  # Key for SMART summary object in API summary response
    ATTR_SMART_RESULTS,  # Key for the list of SMART snapshots in API details response
    # Keys for navigating the aggregated data structure (used internally by the coordin)
    KEY_DETAILS_DEVICE,  # Key for storing detailed device information
    KEY_DETAILS_METADATA,  # Key for storing SMART attribute metadata
    KEY_DETAILS_SMART_LATEST,  # Key for storing the latest SMART snapshot
    KEY_SUMMARY_DEVICE,  # Key for storing summary device information
    KEY_SUMMARY_SMART,  # Key for storing summary SMART information
    # General constants
    LOGGER,  # Logger instance for the integration
)

# Conditional import for type checking, avoids circular imports at runtime.
if TYPE_CHECKING:
    from datetime import timedelta
    from logging import Logger

    from homeassistant.core import HomeAssistant


def _raise_update_failed(message: str, error: Exception) -> NoReturn:
    """
    Helper function to construct and consistently raise an UpdateFailed exception.
    This signals to Home Assistant that the data update attempt failed.

    Args:
        message: The core error message.
        error: The original exception that caused the update failure.

    Raises:
        UpdateFailed: Always raises this exception, chaining the original error.

    """  # noqa: D205, D401
    final_message = f"{message}: {error!s}"
    raise UpdateFailed(final_message) from error


def _raise_scrutiny_api_error_from_coordinator(
    message: str, *, is_response_error: bool = True
) -> NoReturn:
    """
    Helper function to raise a ScrutinyApiError or ScrutinyApiResponseError
    from within the coordinator's logic, typically when validating API data.

    Args:
        message: The error message.
        is_response_error: If True, raises ScrutinyApiResponseError,
        otherwise ScrutinyApiError.

    Raises:
        ScrutinyApiResponseError or ScrutinyApiError.

    """  # noqa: D205, D401
    if is_response_error:
        raise ScrutinyApiResponseError(message)
    raise ScrutinyApiError(message)


class ScrutinyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """
    Manages fetching and coordinating Scrutiny data updates.

    This class polls the Scrutiny API, processes the data, and makes it available
    to entities. The generic type `dict[str, dict[str, Any]]` specifies the
    structure of `self.data`: a dictionary where keys are disk WWNs, and values
    are dictionaries containing aggregated data for that disk (using KEY_... constants).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: Logger,
        name: str,
        api_client: ScrutinyApiClient,
        update_interval: timedelta,
    ) -> None:
        """
        Initialize the data update coordinator.

        Args:
            hass: The Home Assistant instance.
            logger: The logger to use for this coordinator.
            name: A descriptive name for the coordinator (used in logs).
            api_client: An instance of ScrutinyApiClient to interact with the API.
            update_interval: The interval at which to poll for new data.

        """
        self.api_client = api_client
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )
        # This dictionary will store the aggregated data for all disks.
        # Structure: { "wwn1": {KEY_SUMMARY_DEVICE: {...},
        # KEY_DETAILS_SMART_LATEST: {...}, ...}, ... }
        self.aggregated_disk_data: dict[str, dict[str, Any]] = {}

    def _process_detail_results(
        self,
        wwn_key: str,
        full_detail_response: Any,  # Can be the successful response dict or Exception
        target_data_dict: dict[
            str, Any
        ],  # The dict for the current WWN in aggregated_data
    ) -> None:
        """
        Process the result of a single disk's detail fetch operation.
        This method updates `target_data_dict` (which is a part of
        `current_run_aggregated_data` in `_async_update_data`) with the
        details fetched for a specific disk.

        Args:
            wwn_key: The WWN of the disk whose details are being processed.
            full_detail_response: The result from `api_client.async_get_device_details`.
                                  This can be the expected dictionary on success, or an
                                  Exception object if
                                  `asyncio.gather(return_exceptions=True)`
                                  caught an error for this specific task.
            target_data_dict: The dictionary within the main aggregated data structure
                              that corresponds to `wwn_key`. This dictionary will be
                              populated with
                              `KEY_DETAILS_DEVICE`, `KEY_DETAILS_SMART_LATEST`,
                              and `KEY_DETAILS_METADATA`.

        """  # noqa: D205
        if isinstance(full_detail_response, Exception):
            # If fetching details failed for this disk, log a warn and set empty dicts.
            # Sensors relying on this data will then report
            # as unavailable or with default values.
            self.logger.warning(
                (
                    "Failed to fetch details for disk %s: %s. "
                    "Summary data will be used if available."
                ),
                wwn_key,
                full_detail_response,
            )
            target_data_dict[KEY_DETAILS_DEVICE] = {}
            target_data_dict[KEY_DETAILS_SMART_LATEST] = {}
            target_data_dict[KEY_DETAILS_METADATA] = {}
        elif isinstance(full_detail_response, dict):
            # Successfully fetched details. The response is expected to be a dict like:
            # {"data": {"device": ..., "smart_results": [...]},
            #  "metadata": {...}, "success": true}

            # Extract the 'data' part which contains 'device' and 'smart_results'.
            actual_payload = full_detail_response.get("data", {})

            LOGGER.debug(
                (
                    "COORDINATOR _process_detail_results (WWN: %s): "
                    "Full detail response: %s"
                ),
                wwn_key,
                str(full_detail_response)[:500],  # Log first 500 chars
            )
            LOGGER.debug(
                (
                    "COORDINATOR _process_detail_results (WWN: %s): "
                    "Extracted 'actual_payload' (for device/smart_results): %s"
                ),
                wwn_key,
                str(actual_payload)[:500],  # Log first 500 chars
            )

            # Store the 'device' object from the details.
            target_data_dict[KEY_DETAILS_DEVICE] = actual_payload.get(ATTR_DEVICE, {})

            # Extract the latest SMART snapshot from 'smart_results'.
            # 'smart_results' is expected to be a list
            #  of snapshots; we take the first (latest).
            smart_results_list = actual_payload.get(ATTR_SMART_RESULTS, [])
            if (
                smart_results_list
                and isinstance(smart_results_list, list)
                and smart_results_list[
                    0
                ]  # Check if list is not empty and first element exists
            ):
                target_data_dict[KEY_DETAILS_SMART_LATEST] = smart_results_list[0]
            else:
                target_data_dict[KEY_DETAILS_SMART_LATEST] = {}
                self.logger.debug(
                    "No smart_results found or empty in details for disk %s.", wwn_key
                )

            # Extract the 'metadata' for SMART attributes.
            # This metadata is at the top level of the full_detail_response.
            metadata_content = full_detail_response.get(ATTR_METADATA, {})
            target_data_dict[KEY_DETAILS_METADATA] = metadata_content

            LOGGER.debug(
                "COORDINATOR _process_detail_results (WWN: %s): Stored METADATA: %s",
                wwn_key,
                str(metadata_content)[:500],  # Log first 500 chars
            )

        else:
            # Should not happen if API client behaves
            #  as expected (returns dict or raises).
            self.logger.error(
                "Unexpected result type (%s) for disk %s full_detail_response.",
                type(full_detail_response).__name__,
                wwn_key,
            )
            target_data_dict[KEY_DETAILS_DEVICE] = {}
            target_data_dict[KEY_DETAILS_SMART_LATEST] = {}
            target_data_dict[KEY_DETAILS_METADATA] = {}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """
        Fetch the latest summary and detailed disk data from the Scrutiny API.
        This method is called periodically by the DataUpdateCoordinator base class.

        Returns:
            A dictionary where keys are disk WWNs and values are dictionaries
            containing the aggregated summary and detail data for each disk.
            This becomes `self.data` in the coordinator.

        Raises:
            UpdateFailed: If any critical error occurs during the API calls or data processing,
                          preventing a successful update.

        """  # noqa: D205, E501
        self.logger.debug("Starting Scrutiny data update cycle.")

        # This dictionary will hold all data fetched during this specific update run.
        current_run_aggregated_data: dict[str, dict[str, Any]] = {}

        try:
            # 1. Fetch the summary data for all disks.
            # The summary_data is expected to be:
            #  {"wwn1": {"device": ..., "smart": ...}, ...}
            summary_data = await self.api_client.async_get_summary()
            if not isinstance(summary_data, dict):
                # This should ideally be caught by the API client, but double-check.
                _raise_scrutiny_api_error_from_coordinator(
                    "Summary data from API was not a dictionary."
                )

            self.logger.debug(
                "Successfully fetched summary data for %d disk(s).", len(summary_data)
            )

            # Prepare to fetch details for each disk found in the summary.
            detail_tasks = []  # List to hold asyncio tasks for fetching details.
            wwn_order = []  # List to maintain the order of WWNs for matching results.

            for wwn, disk_summary_info in summary_data.items():
                wwn_order.append(wwn)
                # Initialize the structure for this disk in our aggregated data.
                # Populate with summary data first. Detail data will be added later.
                current_run_aggregated_data[wwn] = {
                    KEY_SUMMARY_DEVICE: disk_summary_info.get(
                        ATTR_DEVICE,
                        {},  # API key for device summary is "device"
                    ),
                    KEY_SUMMARY_SMART: disk_summary_info.get(
                        ATTR_SMART,
                        {},  # API key for smart summary is "smart"
                    ),
                    KEY_DETAILS_DEVICE: {},  # Placeholder
                    KEY_DETAILS_SMART_LATEST: {},  # Placeholder
                    KEY_DETAILS_METADATA: {},  # Placeholder
                }
                # Create a task to fetch details for this WWN.
                detail_tasks.append(self.api_client.async_get_device_details(wwn))

            # 2. Fetch detailed data for all disks concurrently.
            if detail_tasks:
                self.logger.debug("Fetching details for %d disk(s).", len(detail_tasks))
                # `asyncio.gather` runs all detail_tasks concurrently.
                # `return_exceptions=True` means if a task raises an exception,
                # the exception object is returned in its place in the results list,
                # rather than stopping all other tasks.
                detail_results = await asyncio.gather(
                    *detail_tasks, return_exceptions=True
                )
                # Process the results (or exceptions) for each disk.
                for i, wwn_key in enumerate(wwn_order):
                    self._process_detail_results(
                        wwn_key, detail_results[i], current_run_aggregated_data[wwn_key]
                    )
            else:
                self.logger.debug("No disks found in summary to fetch details for.")

        except ScrutinyApiConnectionError as err:
            # Handle connection errors (e.g., Scrutiny server down).
            _raise_update_failed(
                "Connection error during Scrutiny data update cycle", err
            )
        except ScrutinyApiError as err:  # Includes ScrutinyApiResponseError
            # Handle other API-specific errors (e.g., bad response format).
            _raise_update_failed(
                f"API error during Scrutiny data update cycle: {err!s}", err
            )
        except Exception as err:
            # Catch any other unexpected errors during the update process.
            self.logger.exception("Unexpected error during Scrutiny data update cycle")
            _raise_update_failed(
                "An unexpected error occurred during Scrutiny data update", err
            )

        self.logger.debug(
            "Scrutiny data update cycle completed. Aggregated data for WWNs: %s",
            list(current_run_aggregated_data.keys()),
        )
        # Store the successfully fetched and processed data.
        # This will become self.data and notify listeners.
        self.aggregated_disk_data = current_run_aggregated_data
        return self.aggregated_disk_data
