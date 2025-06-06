"""DataUpdateCoordinator for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn  # NoReturn for _raise_update_failed

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,  # Exception raised when an update fails
)

from .api import ScrutinyApiClient, ScrutinyApiConnectionError, ScrutinyApiError

if TYPE_CHECKING:
    from datetime import timedelta
    from logging import Logger  # For type hint of logger parameter

    from homeassistant.core import HomeAssistant


def _raise_update_failed(message: str, error: Exception) -> NoReturn:
    """
    Construct and consistently raise an UpdateFailed exception.

    This helper ensures that UpdateFailed exceptions are created with
    a chained original exception, which is good for debugging and adheres
    to Ruff's TRY301 rule by abstracting the `raise` statement.

    Args:
        message: The primary message for the UpdateFailed exception.
        error: The original exception that caused the update failure.

    Raises:
        UpdateFailed: Always raises this exception.

    """
    # Construct the final message, including the original error's string representation.
    final_message = f"{message}: {error!s}"  # Use !s for safe string conversion
    raise UpdateFailed(final_message) from error


class ScrutinyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """
    Manages fetching and coordinating Scrutiny data updates.

    This class polls the Scrutiny API at a regular interval and updates
    any subscribed Home Assistant entities with the new data.
    The generic type `dict[str, Any]` indicates the structure of `self.data`
    (a dictionary, where keys are disk WWNs and values are their data).
    A more precise TypedDict could be used here for stricter type checking.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: Logger,  # The domain-specific logger instance
        name: str,  # A descriptive name for this coordinator instance (used in logs)
        api_client: ScrutinyApiClient,  # The API client to fetch data
        update_interval: timedelta,  # How often to poll the API
    ) -> None:
        """Initialize the data update coordinator."""
        self.api_client = api_client
        # Call the superclass's __init__ method.
        # The logger passed here will be used by the DataUpdateCoordinator base class
        # for its own logging, and accessible via self.logger.
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """
        Fetch the latest data from the Scrutiny API.

        This method is called periodically by the DataUpdateCoordinator.
        It should return the fetched data or raise UpdateFailed on error.

        Returns:
            A dictionary containing the Scrutiny summary data, keyed by disk WWN.

        Raises:
            UpdateFailed: If fetching or processing data fails.

        """
        try:
            # Attempt to get the summary data using the API client.
            summary_data = await self.api_client.async_get_summary()
        except ScrutinyApiConnectionError as err:
            # Handle specific connection errors from the API client.
            # The _raise_update_failed helper will raise UpdateFailed.
            _raise_update_failed("Error communicating with the Scrutiny API", err)
        except ScrutinyApiError as err:
            # Handle other generic API errors from the API client.
            _raise_update_failed("Invalid or error response from the Scrutiny API", err)
        # pylint: disable=broad-except
        except Exception as err:  # Catch any other unexpected exceptions
            # Log the full traceback for unexpected errors.
            self.logger.exception(
                "An unexpected error occurred while fetching Scrutiny data"
            )
            _raise_update_failed(
                "An unexpected error occurred during Scrutiny data fetch", err
            )
        # The 'else' block executes only if the 'try' block was successful.
        else:
            # Perform a basic check on the structure of the returned data.
            if not isinstance(summary_data, dict):
                # If data is not a dictionary, something is wrong with the API response
                # or our parsing of it.
                msg = (
                    "Invalid data structure received from Scrutiny API: "
                    f"expected dict, got {type(summary_data).__name__}"
                )
                # This is a new error condition found after a successful API call.
                raise UpdateFailed(
                    msg
                )  # No "from" needed as it's a new validation failure.
            return summary_data
