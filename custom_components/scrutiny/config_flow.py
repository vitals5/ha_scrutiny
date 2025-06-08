"""Config flow for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from typing import Any  # 'Any' for user_input type hint in async_step_user

import voluptuous as vol  # For defining data validation schemas
from homeassistant import (
    config_entries,
)  # Base class for ConfigFlow, ConfigFlowResult, etc.
from homeassistant.const import CONF_HOST  # Standard Home Assistant constant for host

# Import port constant from our integration's const.py
from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession,
)  # For getting HA's HTTP session

# Import API client and specific exceptions for robust
#  error handling during connection testing.
from .api import (
    ScrutinyApiAuthError,  # For authentication failures
    ScrutinyApiClient,  # The client to interact with Scrutiny API
    ScrutinyApiConnectionError,  # For network/connection issues
    ScrutinyApiResponseError,  # For unexpected API responses
    # ScrutinyApiError, # General base error, caught by specific ones or Exception
)

# Import constants from our integration.
from .const import (
    CONF_PORT,
    DEFAULT_PORT,
    DOMAIN,
    LOGGER,
)  # DOMAIN for config flow, LOGGER for logging

# Data schema for the user configuration form.
# This defines the fields the user will see in the UI, their types, and default values.
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        # Hostname or IP address of the Scrutiny server. This field is required.
        vol.Required(CONF_HOST): str,
        # Port number for the Scrutiny server. This field
        #  is optional and defaults to DEFAULT_PORT.
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class ScrutinyConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Manages the configuration flow for the Scrutiny integration.

    This class handles the steps involved when a user adds or reconfigures
    the integration through the Home Assistant UI.
    """

    VERSION = (
        1  # Version of the config flow. Increment if the schema or stored data changes.
    )
    # Connection class is not used here as we are doing local polling.
    # CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL  # noqa: ERA001

    async def _test_connection(self, host: str, port: int) -> None:
        """
        Test the connection to the Scrutiny API with the provided details.

        This helper method attempts to fetch summary data from the Scrutiny API
        to validate that the provided host and port
          are correct and the API is responsive.

        Args:
            host: The Scrutiny server host.
            port: The Scrutiny server port.

        Raises:
            ScrutinyApiConnectionError: If connection to the Scrutiny server fails
            (e.g., timeout, host not found).
            ScrutinyApiResponseError: If the Scrutiny API responds with an error or
            unexpected data format.
            ScrutinyApiAuthError: If authentication fails (though Scrutiny API
            doesn't typically use auth).
            Other exceptions from ScrutinyApiClient.async_get_summary() might
            also propagate.

        """
        # Get Home Assistant's shared aiohttp client session.
        session = async_get_clientsession(self.hass)
        # Create an instance of our API client.
        client = ScrutinyApiClient(host=host, port=port, session=session)
        # Attempt to fetch summary data. If this call succeeds,
        #  the connection is considered valid.
        # If it fails, it will raise one of the ScrutinyApi*
        #  exceptions, which will be caught
        # by the calling method (async_step_user).
        await client.async_get_summary()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """
        Handle the initial step of the user-initiated config flow.

        This step prompts the user for connection details (host, port),
        validates them by attempting a connection, and then creates a
        config entry if successful.

        Args:
            user_input: A dictionary containing user-provided data from the form.
                        It's None if the form is being shown for the first time.

        Returns:
            A ConfigFlowResult indicating the next step or outcome:
            - self.async_show_form(...): If the form needs to be shown
              (or re-shown due to errors).
            - self.async_create_entry(...): If the input is valid and
              the entry should be created.
            - self.async_abort(...): If the setup should be aborted
              (e.g., already configured).

        """
        errors: dict[
            str, str
        ] = {}  # Dictionary to store validation errors to display in the UI.

        if user_input is not None:
            # User has submitted the form, so process the input.
            host = user_input[CONF_HOST]
            # Get the port, defaulting to DEFAULT_PORT if not provided
            #  or if schema handling is bypassed.
            # The schema already applies the default, but this is a safeguard.
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # Create a unique ID for this configuration entry
            #  to prevent duplicate entries
            # for the same Scrutiny instance.
            unique_id = f"{host}:{port}"
            await self.async_set_unique_id(unique_id)
            # Abort if a config entry with this unique_id already exists.
            # This prevents users from adding the same Scrutiny server multiple times.
            self._abort_if_unique_id_configured()

            try:
                # Attempt to connect to Scrutiny with the provided details.
                # The _test_connection method will raise an exception if it fails.
                LOGGER.debug("Testing connection to Scrutiny at %s:%s", host, port)
                await self._test_connection(host, port)
            except ScrutinyApiConnectionError:
                LOGGER.warning("Connection to Scrutiny failed at %s:%s", host, port)
                # "cannot_connect" is a standard error key defined in Home Assistant
                # or can be a custom key defined in strings.json.
                errors["base"] = "cannot_connect"
            except ScrutinyApiResponseError:
                LOGGER.warning(
                    "Invalid API response from Scrutiny at %s:%s", host, port
                )
                # "invalid_api_response" should be a key in strings.json
                #  for a user-friendly message.
                errors["base"] = "invalid_api_response"
            except ScrutinyApiAuthError:
                # This error is unlikely with the current Scrutiny
                #  API (which is unauthenticated)  # noqa: ERA001
                # but included for robustness or future API changes.
                LOGGER.warning(
                    "Authentication error with Scrutiny at %s:%s (unexpected)",
                    host,
                    port,
                )
                # "invalid_auth" is a standard error key.
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except # noqa: BLE001
                # Catch any other unexpected errors during the connection test.
                LOGGER.exception(
                    """An unexpected error occurred while
                     trying to connect to Scrutiny at %s:%s""",
                    host,
                    port,
                )
                # "unknown" is a standard error key for generic failures.
                errors["base"] = "unknown"
            else:
                # If no exceptions were raised, the connection
                #  and API response are valid.
                LOGGER.info("Successfully connected to Scrutiny at %s:%s", host, port)
                # Create the config entry. The title will be
                #  shown in the integrations list.
                # The data dictionary is stored in the config
                #  entry and used during setup.
                return self.async_create_entry(
                    title=f"Scrutiny ({host}:{port})",  # User-visible title for entry.
                    data={  # Data to be stored in the config entry.
                        CONF_HOST: host,
                        CONF_PORT: port,
                    },
                )

        # If user_input is None (first time the form is shown) or if there were errors
        # during validation, show the configuration form to the user again.
        # `errors` will be passed to the form to display error messages.
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
