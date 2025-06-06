"""Config flow for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from typing import Any  # Any for user_input type hint

import voluptuous as vol  # For defining data schemas
from homeassistant import config_entries  # For ConfigFlow, ConfigFlowResult, etc.
from homeassistant.const import CONF_HOST

# CONF_PORT is defined in our const.py, so import it from there.
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Import API client and specific exceptions for error handling.
from .api import (
    ScrutinyApiAuthError,
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
    # ScrutinyApiError, # General one not caught explicitly if specifics are used
)

# Import constants from our integration.
from .const import CONF_PORT, DEFAULT_PORT, DOMAIN, LOGGER

# Data schema for the user configuration form.
# Defines the fields the user will see and their types/defaults.
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,  # Hostname or IP address of Scrutiny server
        vol.Optional(
            CONF_PORT, default=DEFAULT_PORT
        ): int,  # Port, defaults to DEFAULT_PORT
    }
)


class ScrutinyConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Manages the configuration flow for the Scrutiny integration.

    This class handles the steps involved when a user adds or reconfigures
    the integration through the Home Assistant UI.
    """

    VERSION = 1  # Version of the config flow. Increment if schema changes.

    async def _test_connection(self, host: str, port: int) -> None:
        """
        Test the connection to the Scrutiny API with the provided details.

        This helper attempts to fetch data to validate the connection.

        Args:
            host: The Scrutiny server host.
            port: The Scrutiny server port.

        Raises:
            ScrutinyApiConnectionError: If connection fails.
            ScrutinyApiResponseError: If API responds with an error or unexpected data.
            ScrutinyApiAuthError: If authentication fails (currently not expected).

        """
        session = async_get_clientsession(self.hass)
        client = ScrutinyApiClient(host=host, port=port, session=session)
        # Calling async_get_summary will implicitly test the conn. and API response.
        # It will raise one of the ScrutinyApi* exceptions on failure.
        await client.async_get_summary()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:  # Use HA's ConfigFlowResult alias
        """
        Handle the initial step of the user-initiated config flow.

        This step prompts the user for connection details (host, port) and
        validates them.

        Args:
            user_input: A dictionary containing user-provided data from the form.
                        None if the form is being shown for the first time.

        Returns:
            A FlowResult indicating the next step or
            outcome (form, create_entry, abort).

        """
        errors: dict[str, str] = {}  # Dictionary to store validation errors for the UI.

        if user_input is not None:
            # User has submitted the form, process the input.
            host = user_input[CONF_HOST]
            # Ensure port defaults correctly if not provided
            # or if schema handling is bypassed.
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # Create a unique ID for this configuration entry to prevent duplicates.
            # This unique ID is typically based on stable identifiers like host/port.
            unique_id = f"{host}:{port}"
            await self.async_set_unique_id(unique_id)
            # Abort if a config entry with this unique_id already exists.
            self._abort_if_unique_id_configured()

            try:
                # Attempt to connect to Scrutiny with the provided details.
                await self._test_connection(host, port)
            except ScrutinyApiConnectionError:
                LOGGER.warning("Connection to Scrutiny failed at %s:%s", host, port)
                errors["base"] = "cannot_connect"  # Error key for UI string
            except ScrutinyApiResponseError:
                LOGGER.warning(
                    "Invalid API response from Scrutiny at %s:%s", host, port
                )
                errors["base"] = "invalid_api_response"  # Error key for UI string
            except ScrutinyApiAuthError:
                # This error is unlikely with current
                # Scrutiny API but included for robustness.
                LOGGER.warning(
                    "Authentication error with Scrutiny at %s:%s (unexpected)",
                    host,
                    port,
                )
                errors["base"] = "invalid_auth"  # Error key for UI string
            # pylint: disable=broad-except
            except Exception:  # noqa: BLE001 - Catch any other unexpected errors during validation.
                LOGGER.exception(
                    """An unexpected error occurred
                    while trying to connect to Scrutiny at %s:%s""",
                    host,
                    port,
                )
                errors["base"] = "unknown"  # Generic error key
            else:
                # Connection and API response are valid.
                LOGGER.info("Successfully connected to Scrutiny at %s:%s", host, port)
                # Create the config entry.
                return self.async_create_entry(
                    title=f"Scrutiny ({host}:{port})",  # Title for the entry
                    data={  # Data to be stored in the config entry
                        CONF_HOST: host,
                        CONF_PORT: port,
                    },
                )

        # If user_input is None (first time form is shown) or if there were errors,
        # show the configuration form to the user again.
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
