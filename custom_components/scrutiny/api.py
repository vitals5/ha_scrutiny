"""API client for Scrutiny."""

from __future__ import annotations

import asyncio
import json
from typing import Any, NoReturn

import aiohttp

from .const import LOGGER


class ScrutinyApiError(Exception):
    """Generic Scrutiny API error."""


class ScrutinyApiConnectionError(ScrutinyApiError):
    """
    Scrutiny API connection error.

    Raised for issues like timeouts or host not found.
    """


class ScrutinyApiAuthError(ScrutinyApiError):
    """Scrutiny API authentication error."""


class ScrutinyApiResponseError(ScrutinyApiError):
    """
    Scrutiny API response error.

    Raised for unexpected response format or unsuccessful API calls.
    """


def _construct_api_exception_message(
    base_message: str, url: str | None = None, error: Exception | None = None
) -> str:
    """Construct a standardized message for API exceptions."""
    message = base_message
    if url:
        message += f" at {url}"
    if error:
        message += f": {error!s}"
    return message


def _raise_api_response_error(message: str, original_exception: Exception) -> NoReturn:
    """Raise ScrutinyApiResponseError from an original exception."""
    raise ScrutinyApiResponseError(message) from original_exception


def _raise_api_error(message: str, original_exception: Exception) -> NoReturn:
    """Raise ScrutinyApiError from an original exception."""
    raise ScrutinyApiError(message) from original_exception


class ScrutinyApiClient:
    """Scrutiny API Client."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        """Initialize API client."""
        self._host = host
        self._port = port
        self._session = session
        self._base_url = f"http://{self._host}:{self._port}/api"

    async def _request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make an API request."""
        url = f"{self._base_url}/{endpoint}"
        LOGGER.debug("Requesting Scrutiny data: %s %s", method, url)

        try:
            async with asyncio.timeout(10):
                response = await self._session.request(method, url, ssl=False, **kwargs)
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
            _raise_api_response_error(api_err_msg, exc)
        except aiohttp.ClientError as exc:
            generic_msg = _construct_api_exception_message(
                "A client error occurred with Scrutiny", url
            )
            raise ScrutinyApiConnectionError(generic_msg) from exc

    async def async_get_summary(self) -> dict[str, dict]:
        """Get summary data from Scrutiny."""
        response = None
        try:
            response = await self._request("get", "summary")
            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                text_response = await response.text()
                LOGGER.error(
                    "Unexpected content type from Scrutiny API: %s. Response: %s",
                    content_type,
                    text_response[:200],
                )
                msg = f"Expected JSON from Scrutiny, got {content_type}"
                raise ScrutinyApiResponseError(msg)  # noqa: TRY301
            data = await response.json()
        except json.JSONDecodeError as exc:
            raw_response_text = ""
            if response:
                try:
                    raw_response_text = await response.text()
                    LOGGER.error(
                        "Failed to decode JSON from Scrutiny. Raw response: %s",
                        raw_response_text[:500],
                    )
                except Exception:  # pylint: disable=broad-except # noqa: BLE001
                    LOGGER.error("Failed to decode JSON and could not get raw text.")
            else:
                LOGGER.error("Failed to decode JSON, no response object available.")
            msg = "Invalid JSON response from Scrutiny"
            _raise_api_response_error(msg, exc)
        except ScrutinyApiError:
            raise
        except Exception as exc:  # noqa: BLE001 pylint: disable=broad-except
            LOGGER.exception("Unexpected error processing Scrutiny summary")
            msg = "Unexpected error processing Scrutiny summary"
            _raise_api_error(msg, exc)
        else:
            LOGGER.debug("Scrutiny API response data: %s", data)

            if not isinstance(data, dict) or not data.get("success"):
                err_msg = (
                    "Scrutiny API call not successful or unexpected format: "
                    f"{str(data)[:200]}"
                )
                raise ScrutinyApiResponseError(err_msg)

            summary = data.get("data", {}).get("summary")
            if not isinstance(summary, dict):
                err_msg = (
                    "Scrutiny API 'summary' data is missing or not a dict: "
                    f"{str(data)[:200]}"
                )
                raise ScrutinyApiResponseError(err_msg)
            return summary
