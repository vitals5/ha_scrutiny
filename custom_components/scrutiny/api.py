# api.py
"""API client for interacting with a Scrutiny web server."""

from __future__ import annotations

import asyncio
import json
from typing import Any, NoReturn  # NoReturn for functions that always raise

import aiohttp  # For making asynchronous HTTP requests

# Import logger from the integration's const module
from .const import ATTR_METADATA, LOGGER


# Custom exception classes for Scrutiny API interactions.
class ScrutinyApiError(Exception):
    """Generic base exception for Scrutiny API errors."""


class ScrutinyApiConnectionError(ScrutinyApiError):
    """
    Exception raised for errors when connecting to the Scrutiny API.

    This typically includes network issues like host not found,
    connection refused, or timeouts.
    """


class ScrutinyApiAuthError(ScrutinyApiError):
    """Exception raised for authentication errors with the Scrutiny API."""


class ScrutinyApiResponseError(ScrutinyApiError):
    """
    Exception raised for issues with the Scrutiny API's response.

    This includes unexpected data formats, missing expected fields,
    or if the API itself indicates an error (e.g., 'success: false').
    """


def _construct_api_exception_message(
    base_message: str, url: str | None = None, error: Exception | None = None
) -> str:
    """
    Construct a standardized and informative message for API-related exceptions.

    Args:
        base_message: The core message for the exception.
        url: The URL that was being accessed, if applicable.
        error: The original exception, if any, to include its string representation.

    Returns:
        A formatted exception message string.

    """
    message = base_message
    if url:
        message += f" at {url}"
    if error:
        message += f": {error!s}"
    return message


def _raise_scrutiny_api_response_error(
    message: str,
    original_exception: Exception | None = None,  # Made original_exception optional
) -> NoReturn:
    """
    Helper function to construct and raise a ScrutinyApiResponseError.
    It ensures that the original exception is chained if provided.

    Args:
        message: The error message.
        original_exception: The exception that caused this error, if any.

    Raises:
        ScrutinyApiResponseError: Always raises this exception.

    """  # noqa: D205, D401
    if original_exception:
        raise ScrutinyApiResponseError(message) from original_exception
    raise ScrutinyApiResponseError(message)


def _raise_scrutiny_api_error(message: str, original_exception: Exception) -> NoReturn:
    """
    Helper function to construct and raise a generic ScrutinyApiError.
    It ensures that the original exception is chained.

    Args:
        message: The error message.
        original_exception: The exception that caused this error.

    Raises:
        ScrutinyApiError: Always raises this exception.

    """  # noqa: D205, D401
    raise ScrutinyApiError(message) from original_exception


class ScrutinyApiClient:
    """Client to interact with the Scrutiny API."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        """
        Initialize the API client.

        Args:
            host: The hostname or IP address of the Scrutiny server.
            port: The port number of the Scrutiny server.
            session: An aiohttp.ClientSession instance for making requests.

        """
        self._host = host
        self._port = port
        self._session = session
        # Construct the base URL for all API requests.
        self._base_url = f"http://{self._host}:{self._port}/api"

    async def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """
        Make a generic HTTP request to a Scrutiny API endpoint.

        Args:
            method: The HTTP method (e.g., "get", "post").
            endpoint: The API endpoint path (e.g., "summary", "device/wwn/details").
            **kwargs: Additional arguments to pass to the aiohttp.ClientSession.request
            method.

        Returns:
            An aiohttp.ClientResponse object if the request was successful.

        Raises:
            ScrutinyApiConnectionError: If there's a timeout or connection issue.
            ScrutinyApiAuthError: If an authentication error (401, 403) occurs.
            ScrutinyApiResponseError: If the API returns an HTTP error status.

        """
        url = f"{self._base_url}/{endpoint}"
        LOGGER.debug("Requesting Scrutiny data: %s %s", method, url)

        try:
            # Set a timeout for the request.
            async with asyncio.timeout(10):
                response = await self._session.request(
                    method,
                    url,
                    ssl=False,  # Assuming Scrutiny runs on HTTP locally.
                    **kwargs,
                )
                # Raise an HTTPError for bad responses (4xx or 5xx).
                response.raise_for_status()
                return response
        except TimeoutError as exc:
            # Handle request timeout.
            msg = _construct_api_exception_message(
                "Timeout connecting to Scrutiny", url
            )
            raise ScrutinyApiConnectionError(msg) from exc
        except aiohttp.ClientConnectionError as exc:
            # Handle client-side connection errors (e.g., host not found,
            # connection refused).
            msg = _construct_api_exception_message(
                "Connection error with Scrutiny", url
            )
            raise ScrutinyApiConnectionError(msg) from exc
        except aiohttp.ClientResponseError as exc:
            # Handle HTTP error responses from the server.
            LOGGER.error(
                "HTTP error from Scrutiny API at %s: %s (status: %s)",
                url,
                exc.message,
                exc.status,
            )
            if exc.status in (401, 403):
                # Specific handling for authentication errors.
                auth_msg = _construct_api_exception_message(
                    f"Authentication error with Scrutiny ({exc.status})", error=exc
                )
                raise ScrutinyApiAuthError(auth_msg) from exc

            # For other HTTP errors, raise a response error.
            api_err_msg = _construct_api_exception_message(
                f"Scrutiny API returned an error ({exc.status})", error=exc
            )
            # Pass the original exception to chain it
            _raise_scrutiny_api_response_error(api_err_msg, exc)
        except aiohttp.ClientError as exc:  # Catch other aiohttp client errors
            # Handle other aiohttp client errors.
            generic_msg = _construct_api_exception_message(
                "A client error occurred with Scrutiny", url, error=exc
            )
            raise ScrutinyApiConnectionError(generic_msg) from exc

    async def async_get_summary(self) -> dict[str, dict]:
        """Fetch the summary data from the Scrutiny '/api/summary' endpoint."""
        response_obj: aiohttp.ClientResponse | None = None  # Renamed to avoid conflict
        try:
            # _request can raise ScrutinyApiConnectionError, ScrutinyApiAuthError,
            # or ScrutinyApiResponseError (for HTTP status codes >= 400)
            response_obj = await self._request("get", "summary")
            content_type = response_obj.headers.get("Content-Type", "")

            if "application/json" not in content_type:
                text_response = await response_obj.text()
                LOGGER.error(
                    "Unexpected content type from Scrutiny "
                    "API (summary): %s. Response: %s",
                    content_type,
                    text_response[:200],
                )
                msg = f"Expected JSON from Scrutiny summary, got {content_type}"
                # No original exception here, it's a format issue we found
                _raise_scrutiny_api_response_error(msg)

            data: dict = await response_obj.json()  # Can raise json.JSONDecodeError

        except json.JSONDecodeError as exc:
            raw_response_text = "Could not retrieve raw response for summary."
            if response_obj:
                try:
                    raw_response_text = await response_obj.text()
                    LOGGER.error(
                        "Failed to decode JSON from Scrutiny summary. Raw response: %s",
                        raw_response_text[:500],
                    )
                except Exception:  # noqa: BLE001
                    LOGGER.error(
                        "Failed to decode JSON for summary "
                        "and also failed to get raw text."
                    )
            else:  # Should not happen if _request succeeded before json parsing
                LOGGER.error(
                    "Failed to decode JSON for summary, "
                    "no response object was available."
                )
            msg = "Invalid JSON response received from Scrutiny summary"
            _raise_scrutiny_api_response_error(msg, exc)

        # Specific Scrutiny API errors from _request should be re-raised directly
        except ScrutinyApiConnectionError:
            raise
        except ScrutinyApiAuthError:
            raise
        except ScrutinyApiResponseError:
            raise
        # Catch any other truly unexpected error during the try block
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception(
                "An unexpected error occurred while processing Scrutiny summary data"
            )
            msg = "Unexpected error occurred while processing Scrutiny summary"
            _raise_scrutiny_api_error(
                msg, exc
            )  # This becomes a generic ScrutinyApiError
        # No 'else' block needed here, if an exception occurred, it's handled above.
        # If no exception, we proceed to validate 'data'.

        # Process the successfully parsed JSON data.
        LOGGER.debug("Scrutiny API summary response data: %s", str(data)[:1000])

        if not isinstance(data, dict) or not data.get("success"):
            err_msg = (
                "Scrutiny API summary call not successful or unexpected format: "
                f"{str(data)[:200]}"
            )
            # No original exception here, it's a validation of the parsed data
            _raise_scrutiny_api_response_error(err_msg)

        summary_data = data.get("data", {}).get("summary")
        if not isinstance(summary_data, dict):
            err_msg = (
                "Scrutiny API 'summary' data field is missing or not a dictionary: "
                f"{str(data)[:200]}"
            )
            _raise_scrutiny_api_response_error(err_msg)

        return summary_data

    async def async_get_device_details(self, wwn: str) -> dict[str, Any]:
        """Fetch detailed information for a specific disk."""
        endpoint = f"device/{wwn}/details"
        response_obj: aiohttp.ClientResponse | None = None  # Renamed
        LOGGER.debug("Requesting Scrutiny device details for WWN: %s", wwn)

        try:
            response_obj = await self._request("get", endpoint)
            content_type = response_obj.headers.get("Content-Type", "")

            if "application/json" not in content_type:
                msg = (
                    "Expected JSON from Scrutiny "
                    f"device details (WWN: {wwn}), got {content_type}"
                )
                _raise_scrutiny_api_response_error(msg)

            full_api_response_data: dict = await response_obj.json()

        except json.JSONDecodeError as exc:
            msg = (
                "Invalid JSON response received from "
                f"Scrutiny device details (WWN: {wwn})"
            )
            _raise_scrutiny_api_response_error(msg, exc)

        except ScrutinyApiConnectionError:
            raise
        except ScrutinyApiAuthError:
            raise
        except ScrutinyApiResponseError:
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception(
                "Unexpected error processing Scrutiny device details (WWN: %s)", wwn
            )
            msg = f"Unexpected error processing Scrutiny device details (WWN: {wwn})"
            _raise_scrutiny_api_error(msg, exc)

        # Process the successfully parsed JSON data.
        LOGGER.debug(
            "Scrutiny API device details FULL response for WWN %s: %s",
            wwn,
            str(full_api_response_data)[:2000],
        )

        if not isinstance(
            full_api_response_data, dict
        ) or not full_api_response_data.get("success"):
            err_msg = (
                "Scrutiny API device details call not successful or unexpected format "
                f"(WWN: {wwn}): {str(full_api_response_data)[:200]}"
            )
            _raise_scrutiny_api_response_error(err_msg)

        if (
            "data" not in full_api_response_data
            or ATTR_METADATA not in full_api_response_data
        ):
            err_msg = (
                "Scrutiny API device details "
                "response is missing 'data' or 'metadata' key "
                f"(WWN: {wwn}): Keys present: {list(full_api_response_data.keys())}"
            )
            LOGGER.error(err_msg)
            _raise_scrutiny_api_response_error(err_msg)

        return full_api_response_data
