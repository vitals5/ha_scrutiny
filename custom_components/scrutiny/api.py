"""API client for interacting with a Scrutiny web server."""

from __future__ import annotations

import asyncio
import json
from typing import Any, NoReturn  # NoReturn for functions that always raise

import aiohttp  # For making HTTP requests

from .const import ATTR_METADATA, LOGGER  # Integration-specific logger


# Custom exception classes for Scrutiny API interactions.
class ScrutinyApiError(Exception):
    """Generic base exception for Scrutiny API errors."""


class ScrutinyApiConnectionError(ScrutinyApiError):
    """
    Exception raised for errors when connecting to the Scrutiny API.

    This typically includes network issues like host not found or timeouts.
    """


class ScrutinyApiAuthError(ScrutinyApiError):
    """Exception raised for authentication errors with the Scrutiny API."""


class ScrutinyApiResponseError(ScrutinyApiError):
    """
    Exception raised for issues with the Scrutiny API's response.

    This includes unexpected data formats, or if the API itself indicates an error.
    """


def _construct_api_exception_message(
    base_message: str, url: str | None = None, error: Exception | None = None
) -> str:
    """Construct a standardized and informative message for API-related exceptions."""
    message = base_message
    if url:
        message += f" at {url}"
    if error:
        message += f": {error!s}"
    return message


def _raise_scrutiny_api_response_error(
    message: str, original_exception: Exception
) -> NoReturn:
    """Construct and raise a ScrutinyApiResponseError, chaining the orig exception."""
    raise ScrutinyApiResponseError(message) from original_exception


def _raise_scrutiny_api_error(message: str, original_exception: Exception) -> NoReturn:
    """Construct and raise a ScrutinyApiError, chaining the original exception."""
    raise ScrutinyApiError(message) from original_exception


class ScrutinyApiClient:
    """Client to interact with the Scrutiny API."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._host = host
        self._port = port
        self._session = session
        self._base_url = f"http://{self._host}:{self._port}/api"

    async def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make a generic HTTP request to a Scrutiny API endpoint."""
        url = f"{self._base_url}/{endpoint}"
        LOGGER.debug("Requesting Scrutiny data: %s %s", method, url)

        try:
            async with asyncio.timeout(10):
                response = await self._session.request(
                    method,
                    url,
                    ssl=False,
                    **kwargs,
                )
                response.raise_for_status()
                return response
        except TimeoutError as exc:
            msg = _construct_api_exception_message(
                "Timeout connecting to Scrutiny", url
            )
            raise ScrutinyApiConnectionError(msg) from exc
        except aiohttp.ClientConnectionError as exc:
            msg = _construct_api_exception_message(
                "Connection error with Scrutiny", url
            )
            raise ScrutinyApiConnectionError(msg) from exc
        except aiohttp.ClientResponseError as exc:
            LOGGER.error(
                "HTTP error from Scrutiny API at %s: %s (status: %s)",
                url,
                exc.message,
                exc.status,
            )
            if exc.status in (401, 403):
                auth_msg = _construct_api_exception_message(
                    f"Authentication error with Scrutiny ({exc.status})", error=exc
                )
                raise ScrutinyApiAuthError(auth_msg) from exc

            api_err_msg = _construct_api_exception_message(
                f"Scrutiny API returned an error ({exc.status})", error=exc
            )
            _raise_scrutiny_api_response_error(api_err_msg, exc)
        except aiohttp.ClientError as exc:
            generic_msg = _construct_api_exception_message(
                "A client error occurred with Scrutiny", url
            )
            raise ScrutinyApiConnectionError(generic_msg) from exc

    async def async_get_summary(self) -> dict[str, dict]:
        """Fetch the summary data from the Scrutiny '/api/summary' endpoint."""
        response: aiohttp.ClientResponse | None = None
        try:
            response = await self._request("get", "summary")
            content_type = response.headers.get("Content-Type", "")

            if "application/json" not in content_type:
                text_response = await response.text()
                LOGGER.error(
                    """Unexpected content type from
                      Scrutiny API (summary): %s. Response: %s""",
                    content_type,
                    text_response[:200],
                )
                msg = f"Expected JSON from Scrutiny summary, got {content_type}"
                raise ScrutinyApiResponseError(msg)  # noqa: TRY301

            data: dict = await response.json()

        except json.JSONDecodeError as exc:
            raw_response_text = "Could not retrieve raw response for summary."
            if response:
                try:
                    raw_response_text = await response.text()
                    LOGGER.error(
                        "Failed to decode JSON from Scrutiny summary. Raw response: %s",
                        raw_response_text[:500],
                    )
                # pylint: disable=broad-except
                except Exception:  # noqa: BLE001
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
            raise
        # pylint: disable=broad-except
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception(
                "An unexpected error occurred while processing Scrutiny summary data"
            )
            msg = "Unexpected error occurred while processing Scrutiny summary"
            _raise_scrutiny_api_error(msg, exc)
        else:
            LOGGER.debug("Scrutiny API summary response data: %s", str(data)[:1000])

            if not isinstance(data, dict) or not data.get("success"):
                err_msg = (
                    "Scrutiny API summary call not successful or unexpected format: "
                    f"{str(data)[:200]}"
                )
                raise ScrutinyApiResponseError(err_msg)

            summary_data = data.get("data", {}).get("summary")
            if not isinstance(summary_data, dict):
                err_msg = (
                    "Scrutiny API 'summary' data field is missing or not a dictionary: "
                    f"{str(data)[:200]}"
                )
                raise ScrutinyApiResponseError(err_msg)

            return summary_data

    async def async_get_device_details(
        self, wwn: str
    ) -> dict[str, Any]:  # Rückgabetyp ist jetzt das "Gesamtobjekt"
        """
        Fetch detailed information for a specific disk from Scrutiny.

        Args:
            wwn: The World Wide Name of the disk.

        Returns:
            A dictionary representing the entire successful JSON response,
            which should contain 'data' (with device, smart_results)
            and 'metadata' keys.

        Raises:
            ScrutinyApiResponseError: If API response is not valid JSON,
                                     if `success` is not true.
            (Inherits connection errors from _request method)

        """
        endpoint = f"device/{wwn}/details"
        response: aiohttp.ClientResponse | None = None
        LOGGER.debug("Requesting Scrutiny device details for WWN: %s", wwn)

        try:
            response = await self._request("get", endpoint)
            content_type = response.headers.get("Content-Type", "")

            if "application/json" not in content_type:
                msg = f"Expected JSON from Scrutiny device details, got {content_type}"
                raise ScrutinyApiResponseError(msg)  # noqa: TRY301

            # full_api_response_data ist jetzt die gesamte Antwort,
            # z.B. {"data": {...}, "metadata": {...}, "success": true}
            full_api_response_data: dict = await response.json()

        except json.JSONDecodeError as exc:
            msg = f"""Invalid JSON response received from
              Scrutiny device details (WWN: {wwn})"""
            _raise_scrutiny_api_response_error(msg, exc)
        except ScrutinyApiError:
            raise
        except Exception as exc:  # noqa: BLE001 pylint: disable=broad-except
            msg = f"Unexpected error processing Scrutiny device details (WWN: {wwn})"
            _raise_scrutiny_api_error(msg, exc)
        else:
            LOGGER.debug(
                "Scrutiny API device details FULL response for WWN %s: %s",
                wwn,
                str(full_api_response_data)[:2000],
            )

            if not isinstance(
                full_api_response_data, dict
            ) or not full_api_response_data.get("success"):
                err_msg = (
                    """Scrutiny API device details call
                      not successful or unexpected format """
                    f"(WWN: {wwn}): {str(full_api_response_data)[:200]}"
                )
                raise ScrutinyApiResponseError(err_msg)

            if (
                "data" not in full_api_response_data
                or ATTR_METADATA not in full_api_response_data
            ):  # ATTR_METADATA ist "metadata"
                err_msg = (
                    """Scrutiny API device details response
                      is missing 'data' or 'metadata' key """
                    f"(WWN: {wwn}): Keys present: {list(full_api_response_data.keys())}"
                )
                LOGGER.error(err_msg)
                raise ScrutinyApiResponseError(err_msg)

            return full_api_response_data
