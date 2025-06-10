"""Options flow for the Scrutiny Home Assistant integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol  # For defining data validation schemas
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import InvalidData  # noqa: F401

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    LOGGER,
)


class ScrutinyOptionsFlowHandler(OptionsFlow):
    """Handle Scrutiny options."""

    # The OptionsFlowHandler is automatically registered by Home Assistant
    # when async_get_options_flow is implemented in the ConfigFlowHandler.

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize Scrutiny options flow."""
        self.config_entry = config_entry
        # Store a mutable copy of the current options.
        # This allows us to modify them during the flow steps
        # before saving the final result.
        self.current_options = dict(config_entry.options)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Manage the Scrutiny options."""
        # This is the main step for the options flow.
        # It displays the form and handles user input.
        errors: dict[str, str] = {}

        # Determine the current value for the scan interval field.
        # We prioritize the value from the ongoing
        # options flow (`self.current_options`),
        # then the value already stored in the config entry's options,
        # then the value stored in the config entry's data (from initial setup),
        # and finally the integration's default value.
        current_scan_interval = self.current_options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.options.get(
                # Fallback to data if not in options
                # (shouldn't happen if data is migrated)
                # or if options are empty initially.
                # This ensures the form is pre-filled with the currently active value.
                CONF_SCAN_INTERVAL,
                self.config_entry.data.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES
                ),
            ),
        )

        # Define the schema for the options form.
        # This schema is used for validation.
        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    # Pre-fill the form with the current value.
                    default=current_scan_interval,
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                # Add other options fields here if needed in the future.
            }
        )

        if user_input is not None:
            try:
                validated_input = options_schema(user_input)
                return self.async_create_entry(title="", data=validated_input)
                # `async_create_entry` saves the validated_input
                # into `config_entry.options`
                # and triggers a reload of the integration
                # if needed (handled in __init__.py).

            except vol.MultipleInvalid as ex:
                # Handle validation errors from voluptuous.
                for error in ex.errors:
                    if error.path:
                        # Map the error to the specific field that failed validation.
                        # error.path is a list of keys/indices to the field.
                        errors[str(error.path[0])] = error.msg
                    else:
                        errors["base"] = error.msg
                # Keep the user's input in `self.current_options` so the form
                # is pre-filled with their (potentially invalid) values when re-shown.
                self.current_options.update(user_input)

            except Exception as ex_generic:  # noqa: BLE001
                # Catch any other unexpected errors during validation.
                LOGGER.exception("Unexpected error validating options: %s", ex_generic)
                # "unknown_options_error" should be a key in strings.json
                errors["base"] = "unknown_options_error"

        # If user_input is None (first time showing the form) or if there were errors,
        # prepare the form defaults (including potentially invalid user input
        # so the user doesn't lose their changes) and show the form again.
        form_defaults = self.current_options.copy()
        # Ensure the scan interval default is set, using the determined current value
        # if the user hasn't provided input yet or if their input was invalid.
        if CONF_SCAN_INTERVAL not in form_defaults:
            form_defaults[CONF_SCAN_INTERVAL] = current_scan_interval
        # Note: The schema definition here is slightly redundant with the one above,
        # but explicitly setting the default here
        # ensures the form is populated correctly
        # even after invalid input.

        options_schema_with_user_values = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=form_defaults.get(
                        CONF_SCAN_INTERVAL, current_scan_interval
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, msg="Scan interval must be at least 1 minute"),
                    # Custom error message for the range validation.
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema_with_user_values,
            # Pass the errors dictionary to display messages next to the fields.
            errors=errors,
        )
