"""Config flow for the Scrutiny Home Assistant integration."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ScrutinyApiAuthError,
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
)
from .const import (
    CONF_ENABLE_ALL_ATTRS,
    CONF_ENABLE_CRITICAL_ATTRS,
    CONF_ENABLE_RAW_VALUES,
    CONF_SCAN_INTERVAL,
    CONF_SHOW_ARCHIVED,
    CONF_URL,
    CONF_VERIFY_SSL,
    DEFAULT_ENABLE_ALL_ATTRS,
    DEFAULT_ENABLE_CRITICAL_ATTRS,
    DEFAULT_ENABLE_RAW_VALUES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_SHOW_ARCHIVED,
    DEFAULT_URL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    LOGGER,
)
from .options_flow import ScrutinyOptionsFlowHandler


def _build_connection_schema(
    url: str = DEFAULT_URL,
    verify_ssl: bool = DEFAULT_VERIFY_SSL,
) -> vol.Schema:
    """
    Schema for connection settings only (used by Reconfigure).

    URL and SSL verification are the only fields that affect connectivity.
    All optional tuning belongs in the Options flow.
    """
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=url): str,
            vol.Optional(CONF_VERIFY_SSL, default=verify_ssl): bool,
        }
    )


def _build_setup_schema(
    url: str = DEFAULT_URL,
    verify_ssl: bool = DEFAULT_VERIFY_SSL,
    scan_interval: int = DEFAULT_SCAN_INTERVAL_MINUTES,
    show_archived: bool = DEFAULT_SHOW_ARCHIVED,
    enable_critical_attrs: bool = DEFAULT_ENABLE_CRITICAL_ATTRS,
    enable_all_attrs: bool = DEFAULT_ENABLE_ALL_ATTRS,
    enable_raw_values: bool = DEFAULT_ENABLE_RAW_VALUES,
) -> vol.Schema:
    """
    Schema for the initial setup step.

    Shows connection settings and all options together so the user can
    configure everything in one place when first adding the integration.
    The same options are subsequently editable via the Configure (gear) screen.
    """
    return vol.Schema(
        {
            vol.Required(CONF_URL, default=url): str,
            vol.Optional(CONF_VERIFY_SSL, default=verify_ssl): bool,
            vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
            vol.Optional(CONF_SHOW_ARCHIVED, default=show_archived): bool,
            vol.Optional(
                CONF_ENABLE_CRITICAL_ATTRS, default=enable_critical_attrs
            ): bool,
            vol.Optional(CONF_ENABLE_ALL_ATTRS, default=enable_all_attrs): bool,
            vol.Optional(CONF_ENABLE_RAW_VALUES, default=enable_raw_values): bool,
        }
    )


class ScrutinyConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow handler for the Scrutiny integration."""

    VERSION = 2

    async def _test_connection(self, url: str, verify_ssl: bool) -> None:
        """
        Verify connectivity to the Scrutiny API.

        Raises a ``ScrutinyApi*`` exception on failure so callers can map it to
        a user-visible error key.
        """
        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        client = ScrutinyApiClient(base_url=url, session=session)
        await client.async_get_summary()

    async def _validate_input(self, url: str, verify_ssl: bool) -> dict[str, str]:
        """Run a test connection and return an errors dict (empty on success)."""
        errors: dict[str, str] = {}
        try:
            LOGGER.debug("Testing connection to Scrutiny at %s", url)
            await self._test_connection(url, verify_ssl)
        except ScrutinyApiConnectionError:
            LOGGER.warning("Connection to Scrutiny failed at %s", url)
            errors["base"] = "cannot_connect"
        except ScrutinyApiResponseError:
            LOGGER.warning("Invalid API response from Scrutiny at %s", url)
            errors["base"] = "invalid_api_response"
        except ScrutinyApiAuthError:
            LOGGER.warning("Authentication error with Scrutiny at %s", url)
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except  # noqa: BLE001
            LOGGER.exception("Unexpected error while connecting to Scrutiny at %s", url)
            errors["base"] = "unknown"
        return errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """
        Handle the initial setup step.

        Shows connection settings alongside all tuning options so the user
        can configure everything in one step.  Connection settings go to
        ``data``; options go to ``options`` so they remain editable via
        the Configure (gear) screen without reconfiguring the connection.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            url: str = user_input[CONF_URL].rstrip("/")
            verify_ssl: bool = bool(user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))

            unique_id = url
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            errors = await self._validate_input(url, verify_ssl)
            if not errors:
                LOGGER.info("Successfully connected to Scrutiny at %s", url)
                return self.async_create_entry(
                    title=f"Scrutiny ({url})",
                    data={
                        CONF_URL: url,
                        CONF_VERIFY_SSL: verify_ssl,
                    },
                    options={
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
                        ),
                        CONF_SHOW_ARCHIVED: bool(
                            user_input.get(CONF_SHOW_ARCHIVED, DEFAULT_SHOW_ARCHIVED)
                        ),
                        CONF_ENABLE_CRITICAL_ATTRS: bool(
                            user_input.get(
                                CONF_ENABLE_CRITICAL_ATTRS,
                                DEFAULT_ENABLE_CRITICAL_ATTRS,
                            )
                        ),
                        CONF_ENABLE_ALL_ATTRS: bool(
                            user_input.get(
                                CONF_ENABLE_ALL_ATTRS, DEFAULT_ENABLE_ALL_ATTRS
                            )
                        ),
                        CONF_ENABLE_RAW_VALUES: bool(
                            user_input.get(
                                CONF_ENABLE_RAW_VALUES, DEFAULT_ENABLE_RAW_VALUES
                            )
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_setup_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """
        Allow changing host or port of an existing entry.

        Useful when the Scrutiny server moves to a different address.
        All optional tuning (scan interval, entity level, archived disks)
        is handled exclusively in the Options flow (gear icon).
        """
        entry = self._get_reconfigure_entry()

        current_url: str = entry.data.get(CONF_URL, DEFAULT_URL)
        current_verify_ssl: bool = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

        errors: dict[str, str] = {}

        if user_input is not None:
            url: str = user_input[CONF_URL].rstrip("/")
            verify_ssl: bool = bool(user_input.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))

            errors = await self._validate_input(url, verify_ssl)
            if not errors:
                LOGGER.info("Scrutiny entry reconfigured to %s", url)
                return self.async_update_reload_and_abort(
                    entry,
                    title=f"Scrutiny ({url})",
                    data={
                        CONF_URL: url,
                        CONF_VERIFY_SSL: verify_ssl,
                    },
                    reason="reconfigure_successful",
                )

            return self.async_show_form(
                step_id="reconfigure",
                data_schema=_build_connection_schema(url, verify_ssl),
                errors=errors,
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_connection_schema(current_url, current_verify_ssl),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ScrutinyOptionsFlowHandler:
        """Return the options flow handler for this config entry."""
        return ScrutinyOptionsFlowHandler()
