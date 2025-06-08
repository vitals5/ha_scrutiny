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
    message: str, original_exception: Exception
) -> NoReturn:
    """
    Helper function to construct and raise a ScrutinyApiResponseError.
    It ensures that the original exception is chained.

    Args:
        message: The error message.
        original_exception: The exception that caused this error.

    Raises:
        ScrutinyApiResponseError: Always raises this exception.

    """  # noqa: D205, D401
    raise ScrutinyApiResponseError(message) from original_exception


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
            _raise_scrutiny_api_response_error(api_err_msg, exc)
        except aiohttp.ClientError as exc:
            # Handle other aiohttp client errors.
            generic_msg = _construct_api_exception_message(
                "A client error occurred with Scrutiny", url
            )
            raise ScrutinyApiConnectionError(generic_msg) from exc

    async def async_get_summary(self) -> dict[str, dict]:
        """
        Fetch the summary data from the Scrutiny '/api/summary' endpoint.
        The summary typically contains a dictionary where keys are WWNs and
        values are objects with 'device' and 'smart' information for each disk.

        Returns:
            A dictionary containing the 'summary' part of the API response data,
            which maps WWNs to disk summary information.

        Raises:
            ScrutinyApiResponseError: If the response is not valid JSON,
                                     if 'success' is not true in the response,
                                     or if the 'summary' data field is missing/invalid.
            ScrutinyApiConnectionError: Inherited from _request if connection fails.
            ScrutinyApiError: For other unexpected errors during processing.

        """  # noqa: D205
        response: aiohttp.ClientResponse | None = None
        try:
            response = await self._request("get", "summary")
            content_type = response.headers.get("Content-Type", "")

            if "application/json" not in content_type:
                # Log and raise if the content type is not JSON.
                text_response = await response.text()
                LOGGER.error(
                    """Unexpected content type from Scrutiny API
                     (summary): %s. Response: %s""",
                    content_type,
                    text_response[:200],  # Log first 200 chars of response
                )
                msg = f"Expected JSON from Scrutiny summary, got {content_type}"
                # This raise is correct, it's an issue with the response format.
                raise ScrutinyApiResponseError(msg)  # noqa: TRY301

            # Attempt to parse the JSON response.
            data: dict = await response.json()

        except json.JSONDecodeError as exc:
            # Handle errors in decoding JSON.
            raw_response_text = "Could not retrieve raw response for summary."
            if response:
                try:
                    raw_response_text = await response.text()
                    LOGGER.error(
                        "Failed to decode JSON from Scrutiny summary. Raw response: %s",
                        raw_response_text[:500],  # Log first 500 chars
                    )
                except Exception:  # pylint: disable=broad-except # noqa: BLE001
                    LOGGER.error(
                        """Failed to decode JSON for summary
                        and also failed to get raw text."""
                    )
            else:
                LOGGER.error(
                    """Failed to decode JSON for summary,
                     no response object was available."""
                )

            msg = "Invalid JSON response received from Scrutiny summary"
            _raise_scrutiny_api_response_error(msg, exc)
        except ScrutinyApiError:
            # Re-raise ScrutinyApiError and its subclasses if already caught.
            raise
        except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
            # Handle any other unexpected errors.
            LOGGER.exception(
                "An unexpected error occurred while processing Scrutiny summary data"
            )
            msg = "Unexpected error occurred while processing Scrutiny summary"
            _raise_scrutiny_api_error(msg, exc)
        else:
            # Process the successfully parsed JSON data.
            LOGGER.debug(
                "Scrutiny API summary response data: %s", str(data)[:1000]
            )  # Log first 1000 chars

            # Validate the structure of the response.
            if not isinstance(data, dict) or not data.get("success"):
                err_msg = (
                    "Scrutiny API summary call not successful or unexpected format: "
                    f"{str(data)[:200]}"  # Log first 200 chars
                )
                raise ScrutinyApiResponseError(err_msg)

            # Extract the actual summary data.
            summary_data = data.get("data", {}).get("summary")
            if not isinstance(summary_data, dict):
                err_msg = (
                    "Scrutiny API 'summary' data field is missing or not a dictionary: "
                    f"{str(data)[:200]}"  # Log first 200 chars
                )
                raise ScrutinyApiResponseError(err_msg)

            return summary_data

    async def async_get_device_details(self, wwn: str) -> dict[str, Any]:
        """
        Fetch detailed information for a specific disk from Scrutiny's
        '/api/device/{wwn}/details' endpoint.

        Args:
            wwn: The World Wide Name of the disk.

        Returns:
            A dictionary representing the entire successful JSON response from the API.
            This typically includes 'data' (containing 'device' and 'smart_results')
            and 'metadata' (for SMART attribute descriptions).

        Raises:
            ScrutinyApiResponseError: If API response is not valid JSON,
                                     if `success` is not true in the response,
                                     or if essential keys like 'data' or 'metadata' are missing.
            ScrutinyApiConnectionError: Inherited from _request if connection fails.
            ScrutinyApiError: For other unexpected errors during processing.

        """  # noqa: D205, E501
        endpoint = f"device/{wwn}/details"
        response: aiohttp.ClientResponse | None = None
        LOGGER.debug("Requesting Scrutiny device details for WWN: %s", wwn)

        try:
            response = await self._request("get", endpoint)
            content_type = response.headers.get("Content-Type", "")

            if "application/json" not in content_type:
                # Log and raise if the content type is not JSON.
                msg = f"Expected JSON from Scrutiny device details, got {content_type}"
                raise ScrutinyApiResponseError(msg)  # noqa: TRY301

            # Parse the entire JSON response.
            full_api_response_data: dict = await response.json()

        except json.JSONDecodeError as exc:
            # Handle errors in decoding JSON.
            msg = f"""Invalid JSON response received from
             Scrutiny device details (WWN: {wwn})"""
            _raise_scrutiny_api_response_error(msg, exc)
        except ScrutinyApiError:
            # Re-raise ScrutinyApiError and its subclasses.
            raise
        except Exception as exc:  # pylint: disable=broad-except # noqa: BLE001
            # Handle any other unexpected errors.
            msg = f"Unexpected error processing Scrutiny device details (WWN: {wwn})"
            _raise_scrutiny_api_error(msg, exc)
        else:
            # Process the successfully parsed JSON data.
            LOGGER.debug(
                "Scrutiny API device details FULL response for WWN %s: %s",
                wwn,
                str(full_api_response_data)[:2000],  # Log first 2000 chars
            )

            # Validate the structure of the response.
            if not isinstance(
                full_api_response_data, dict
            ) or not full_api_response_data.get("success"):
                err_msg = (
                    """Scrutiny API device details call
                    not successful or unexpected format """
                    # Log first 200 chars
                    f"(WWN: {wwn}): {str(full_api_response_data)[:200]}"
                )
                raise ScrutinyApiResponseError(err_msg)

            # Ensure essential top-level keys 'data' and 'metadata' are present.
            # ATTR_METADATA is "metadata" from const.py
            if (
                "data" not in full_api_response_data
                or ATTR_METADATA not in full_api_response_data
            ):
                err_msg = (
                    """Scrutiny API device details response
                    is missing 'data' or 'metadata' key """
                    f"(WWN: {wwn}): Keys present: {list(full_api_response_data.keys())}"
                )
                LOGGER.error(err_msg)
                raise ScrutinyApiResponseError(err_msg)

            return full_api_response_data
