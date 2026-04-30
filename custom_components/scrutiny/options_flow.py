"""Options flow for the Scrutiny Home Assistant integration."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import OptionsFlow

from .const import (
    CONF_ENABLE_ALL_ATTRS,
    CONF_ENABLE_CRITICAL_ATTRS,
    CONF_ENABLE_RAW_VALUES,
    CONF_SCAN_INTERVAL,
    CONF_SHOW_ARCHIVED,
    DEFAULT_ENABLE_ALL_ATTRS,
    DEFAULT_ENABLE_CRITICAL_ATTRS,
    DEFAULT_ENABLE_RAW_VALUES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DEFAULT_SHOW_ARCHIVED,
    LOGGER,
)


class ScrutinyOptionsFlowHandler(OptionsFlow):
    """Handle options for an existing Scrutiny config entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Show and handle the options form."""
        errors: dict[str, str] = {}

        # Resolve currently active values, preferring options over original data.
        current_scan_interval: int = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
            ),
        )
        current_show_archived: bool = self.config_entry.options.get(
            CONF_SHOW_ARCHIVED, DEFAULT_SHOW_ARCHIVED
        )
        current_critical_attrs: bool = self.config_entry.options.get(
            CONF_ENABLE_CRITICAL_ATTRS, DEFAULT_ENABLE_CRITICAL_ATTRS
        )
        current_all_attrs: bool = self.config_entry.options.get(
            CONF_ENABLE_ALL_ATTRS, DEFAULT_ENABLE_ALL_ATTRS
        )
        current_raw_values: bool = self.config_entry.options.get(
            CONF_ENABLE_RAW_VALUES, DEFAULT_ENABLE_RAW_VALUES
        )

        if user_input is not None:
            try:
                value = int(user_input.get(CONF_SCAN_INTERVAL, current_scan_interval))
                if value < 1:
                    errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
                else:
                    return self.async_create_entry(
                        title="",
                        data={
                            CONF_SCAN_INTERVAL: value,
                            CONF_SHOW_ARCHIVED: bool(
                                user_input.get(
                                    CONF_SHOW_ARCHIVED, current_show_archived
                                )
                            ),
                            CONF_ENABLE_CRITICAL_ATTRS: bool(
                                user_input.get(
                                    CONF_ENABLE_CRITICAL_ATTRS, current_critical_attrs
                                )
                            ),
                            CONF_ENABLE_ALL_ATTRS: bool(
                                user_input.get(CONF_ENABLE_ALL_ATTRS, current_all_attrs)
                            ),
                            CONF_ENABLE_RAW_VALUES: bool(
                                user_input.get(
                                    CONF_ENABLE_RAW_VALUES, current_raw_values
                                )
                            ),
                        },
                    )
            except (TypeError, ValueError):  # fmt: skip
                errors[CONF_SCAN_INTERVAL] = "invalid_scan_interval"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected error validating Scrutiny options")
                errors["base"] = "unknown_options_error"

            # On error, keep the user's submitted values as defaults.
            current_scan_interval = user_input.get(
                CONF_SCAN_INTERVAL, current_scan_interval
            )
            current_show_archived = user_input.get(
                CONF_SHOW_ARCHIVED, current_show_archived
            )
            current_critical_attrs = user_input.get(
                CONF_ENABLE_CRITICAL_ATTRS, current_critical_attrs
            )
            current_all_attrs = user_input.get(CONF_ENABLE_ALL_ATTRS, current_all_attrs)
            current_raw_values = user_input.get(
                CONF_ENABLE_RAW_VALUES, current_raw_values
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current_scan_interval,
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_SHOW_ARCHIVED,
                        default=current_show_archived,
                    ): bool,
                    vol.Optional(
                        CONF_ENABLE_CRITICAL_ATTRS,
                        default=current_critical_attrs,
                    ): bool,
                    vol.Optional(
                        CONF_ENABLE_ALL_ATTRS,
                        default=current_all_attrs,
                    ): bool,
                    vol.Optional(
                        CONF_ENABLE_RAW_VALUES,
                        default=current_raw_values,
                    ): bool,
                }
            ),
            errors=errors,
        )
