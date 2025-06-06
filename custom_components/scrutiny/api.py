"""API client for interacting with a Scrutiny web server."""

from __future__ import annotations

import asyncio
import json
from typing import Any, NoReturn  # NoReturn for functions that always raise

import aiohttp  # For making HTTP requests

from .const import LOGGER  # Integration-specific logger

# Custom exception classes for Scrutiny API interactions.
# These allow for more specific error handling in the coordinator and config flow.


class ScrutinyApiError(Exception):
    """Generic base exception for Scrutiny API errors."""


class ScrutinyApiConnectionError(ScrutinyApiError):
    """
    Exception raised for errors when connecting to the Scrutiny API.

    This typically includes network issues like host not found or timeouts.
    """


class ScrutinyApiAuthError(ScrutinyApiError):
    """Exception raised for authentication errors with the Scrutiny API."""

    # Note: The /api/summary endpoint currently does not require authentication.
    # This is included for completeness or future Scrutiny API changes.


class ScrutinyApiResponseError(ScrutinyApiError):
    """
    Exception raised for issues with the Scrutiny API's response.

    This includes unexpected data formats, or if the API itself indicates an error
    (e.g., `success: false` in the response).
    """


def _construct_api_exception_message(
    base_message: str, url: str | None = None, error: Exception | None = None
) -> str:
    """
    Construct a standardized and informative message for API-related exceptions.

    Args:
        base_message: The core message for the exception.
        url: The URL that was being accessed, if applicable.
        error: The original exception that caused this, if applicable.

    Returns:
        A formatted exception message string.

    """
    message = base_message
    if url:
        message += f" at {url}"
    if error:
        # Use !s for safe string conversion of the original error.
        message += f": {error!s}"
    return message


# Helper functions to raise specific API errors, primarily for Ruff's TRY301 compliance.
# These ensure that 'raise ... from ...' statements are encapsulated.


def _raise_scrutiny_api_response_error(
    message: str, original_exception: Exception
) -> NoReturn:
    """Construct and raise a ScrutinyApiResponseError, chaining the original excep."""
    raise ScrutinyApiResponseError(message) from original_exception


def _raise_scrutiny_api_error(message: str, original_exception: Exception) -> NoReturn:
    """Construct and raise a ScrutinyApiError, chaining the original exception."""
    raise ScrutinyApiError(message) from original_exception


class ScrutinyApiClient:
    """Client to interact with the Scrutiny API."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        """
        Initialize the API client.

        Args:
            host: The hostname or IP address of the Scrutiny server.
            port: The port number the Scrutiny server is listening on.
            session: The aiohttp.ClientSession to use for requests (provided by HA).

        """
        self._host = host
        self._port = port
        self._session = session
        self._base_url = f"http://{self._host}:{self._port}/api"

    async def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """
        Make a generic HTTP request to a Scrutiny API endpoint.

        Handles common request logic, timeouts, and basic error conversion.

        Args:
            method: The HTTP method (e.g., "get", "post").
            endpoint: The API endpoint path (e.g., "summary").
            **kwargs: Additional keyword arguments to pass to aiohttp's request method.

        Returns:
            The aiohttp.ClientResponse object on success.

        Raises:
            ScrutinyApiConnectionError: If a conn. error (timeout, DNS failure) occurs.
            ScrutinyApiAuthError: If an authentication error (401, 403) occurs.
            ScrutinyApiResponseError: If the API returns error statuses (4xx, 5xx).

        """
        url = f"{self._base_url}/{endpoint}"
        LOGGER.debug("Requesting Scrutiny data: %s %s", method, url)

        try:
            # Use a timeout for the request to prevent indefinite blocking.
            async with asyncio.timeout(10):  # 10-second timeout
                response = await self._session.request(
                    method,
                    url,
                    ssl=False,  # Assuming Scrutiny runs on HTTP by default
                    **kwargs,
                )
                # Raise an aiohttp.ClientResponseError for bad HTTP codes (4xx or 5xx).
                response.raise_for_status()
                return response
        except TimeoutError as exc:
            # Handle request timeout specifically.
            msg = _construct_api_exception_message(
                "Timeout connecting to Scrutiny", url
            )
            raise ScrutinyApiConnectionError(msg) from exc
        except aiohttp.ClientConnectionError as exc:
            # Handle lower-level errors (DNS resolution failed, connection refused).
            msg = _construct_api_exception_message(
                "Connection error with Scrutiny", url
            )
            raise ScrutinyApiConnectionError(msg) from exc
        except aiohttp.ClientResponseError as exc:
            # Handle HTTP errors reported by the server (4xx, 5xx status codes).
            LOGGER.error(
                "HTTP error from Scrutiny API at %s: %s (status: %s)",
                url,
                exc.message,
                exc.status,
            )
            if exc.status in (401, 403):  # Example for potential future authentication
                auth_msg = _construct_api_exception_message(
                    f"Authentication error with Scrutiny ({exc.status})", error=exc
                )
                raise ScrutinyApiAuthError(auth_msg) from exc

            # For other HTTP errors, raise a generic response error.
            api_err_msg = _construct_api_exception_message(
                f"Scrutiny API returned an error ({exc.status})", error=exc
            )
            _raise_scrutiny_api_response_error(api_err_msg, exc)  # Use helper
        except aiohttp.ClientError as exc:
            # Catch other, more generic aiohttp client errors.
            generic_msg = _construct_api_exception_message(
                "A client error occurred with Scrutiny", url
            )
            raise ScrutinyApiConnectionError(generic_msg) from exc

    async def async_get_summary(self) -> dict[str, dict]:
        """
        Fetch the summary data from the Scrutiny '/api/summary' endpoint.

        This endpoint provides an overview of all monitored disks.

        Returns:
            A dictionary containing the 'summary' data, where keys are disk WWNs
            and values are objects with 'device' and 'smart' details.

        Raises:
            ScrutinyApiResponseError: If the API response is not valid JSON,
                                     if `success` is not true, or if the expected
                                     data structure ('data.summary') is missing.
            ScrutinyApiError: For other unexpected processing errors.
            (Inherits connection errors from _request method)

        """
        response: aiohttp.ClientResponse | None = (
            None  # Ensure response is defined for except block
        )
        try:
            response = await self._request("get", "summary")
            content_type = response.headers.get("Content-Type", "")

            if "application/json" not in content_type:
                # If the content type is not JSON, log the issue and raise an error.
                text_response = await response.text()
                LOGGER.error(
                    "Unexpected content type from Scrutiny API: %s. Response: %s",
                    content_type,
                    text_response[:200],  # Log only a snippet of the response
                )
                msg = f"Expected JSON from Scrutiny, got {content_type}"
                # This raise is in the try-block, not an except-block.
                # Ruff TRY301 should not apply here typically, but if it does:
                raise ScrutinyApiResponseError(msg)  # noqa: TRY301

            # Attempt to parse the JSON response.
            data: dict = await response.json()

        except json.JSONDecodeError as exc:
            # Handle cases where the response claims to be JSON but isn't valid.
            raw_response_text = "Could not retrieve raw response."
            if response:
                try:
                    raw_response_text = await response.text()
                    LOGGER.error(
                        "Failed to decode JSON from Scrutiny. Raw response: %s",
                        raw_response_text[:500],  # Log a larger snippet for debugging
                    )
                # pylint: disable=broad-except
                except Exception:  # noqa: BLE001 - Catching broad exception during error handling
                    LOGGER.error(
                        "Failed to decode JSON and also fail to get raw text response."
                    )
            else:
                LOGGER.error(
                    "Failed to decode JSON, and no response object was available."
                )

            msg = "Invalid JSON response received from Scrutiny"
            _raise_scrutiny_api_response_error(msg, exc)  # Use helper

        # Re-raise ScrutinyApiError or its subclasses if they were already caught
        # and processed (e.g., by _request).
        except ScrutinyApiError:
            raise

        # Catch any other unexpected exceptions during the summary processing.
        # pylint: disable=broad-except
        except Exception as exc:  # noqa: BLE001 - Intentional broad catch for API client robustness
            LOGGER.exception(
                "An unexpected error occurred while processing Scrutiny summary data"
            )
            msg = "Unexpected error occurred while processing Scrutiny summary"
            _raise_scrutiny_api_error(msg, exc)  # Use helper

        # This 'else' block executes only if the 'try' block completes without except.
        else:
            LOGGER.debug(
                "Scrutiny API response data: %s", str(data)[:1000]
            )  # Log snippet of data

            # Validate the structure of the successful JSON response.
            if not isinstance(data, dict) or not data.get("success"):
                err_msg = (
                    """Scrutiny API call not successful or
                    response format is unexpected: """
                    f"{str(data)[:200]}"  # Include a snippet of the problematic data
                )
                # This raise is part of data validation, not an except block.
                raise ScrutinyApiResponseError(err_msg)

            summary_data = data.get("data", {}).get("summary")
            if not isinstance(summary_data, dict):
                err_msg = (
                    "Scrutiny API 'summary' data field is missing or not a dictionary: "
                    f"{str(data)[:200]}"
                )
                raise ScrutinyApiResponseError(err_msg)

            return summary_data
