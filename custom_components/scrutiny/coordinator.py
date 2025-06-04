"""DataUpdateCoordinator for the Scrutiny integration."""

from __future__ import annotations

from datetime import (
    timedelta,
)
from logging import (
    Logger,
)
from typing import Any, NoReturn

from homeassistant.core import (
    HomeAssistant,
)
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import ScrutinyApiClient, ScrutinyApiConnectionError, ScrutinyApiError
from .const import LOGGER


def _raise_update_failed(message: str, error: Exception) -> NoReturn:
    """
    Construct and raise an UpdateFailed exception.

    This centralizes message formatting for exceptions and handles the raise,
    adhering to Ruff rules like EM101/EM102 and TRY003.
    """
    final_message = f"{message}: {error!s}"
    raise UpdateFailed(final_message) from error


class ScrutinyDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage fetching Scrutiny data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: Logger,
        name: str,
        api_client: ScrutinyApiClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        self.api_client = api_client
        super().__init__(
            hass,
            logger,
            name=name,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Scrutiny API."""
        try:
            summary_data = await self.api_client.async_get_summary()
        except ScrutinyApiConnectionError as err:
            _raise_update_failed("Error communicating with Scrutiny API", err)
        except ScrutinyApiError as err:
            _raise_update_failed("Invalid response from Scrutiny API", err)
        except Exception as err:  # pylint: disable=broad-except
            self.logger.exception("Unexpected error fetching Scrutiny data")
            _raise_update_failed(
                "An unexpected error occurred while fetching data", err
            )
        else:
            if not isinstance(summary_data, dict):
                msg = (
                    "Invalid data structure from Scrutiny API: "
                    f"expected dict, got {type(summary_data).__name__}"
                )
                raise UpdateFailed(msg)
            return summary_data
