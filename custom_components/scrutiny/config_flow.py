"""Config flow for Scrutiny."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
)

import voluptuous as vol
from homeassistant import (
    config_entries,
)
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ScrutinyApiAuthError,
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
)
from .const import CONF_PORT, DEFAULT_PORT, DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.data_entry_flow import FlowResult

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class ScrutinyConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Scrutiny."""

    VERSION = 1

    async def _test_connection(self, host: str, port: int) -> None:
        """Test connection to the Scrutiny API."""
        session = async_get_clientsession(self.hass)
        client = ScrutinyApiClient(host=host, port=port, session=session)
        await client.async_get_summary()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            unique_id = f"{host}:{port}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                await self._test_connection(host, port)
            except ScrutinyApiConnectionError:
                LOGGER.warning("Failed to connect to Scrutiny at %s:%s", host, port)
                errors["base"] = "cannot_connect"
            except ScrutinyApiResponseError:
                LOGGER.warning(
                    "Invalid response from Scrutiny API at %s:%s", host, port
                )
                errors["base"] = "invalid_api_response"
            except ScrutinyApiAuthError:
                LOGGER.warning(
                    "Authentication error with Scrutiny at %s:%s (unexpected)",
                    host,
                    port,
                )
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001 pylint: disable=broad-except
                LOGGER.exception(
                    "Unexpected error connecting to Scrutiny at %s:%s", host, port
                )
                errors["base"] = "unknown"
            else:
                LOGGER.info("Successfully connected to Scrutiny at %s:%s", host, port)
                return self.async_create_entry(
                    title=f"Scrutiny ({host}:{port})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
