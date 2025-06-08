# tests/test_api.py

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
import json  # Für json.JSONDecodeError


# Importiere die Klassen und Exceptions, die du testen möchtest
from custom_components.scrutiny.api import (
    ScrutinyApiClient,
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
    ScrutinyApiAuthError,
)
from custom_components.scrutiny.const import (
    ATTR_DEVICE,
    ATTR_METADATA,
    ATTR_SMART,
    ATTR_SMART_RESULTS,
)

# Definiere einige Konstanten für die Tests
# Diese Werte sind für das Mocking von _request nicht kritisch,
# aber der Client braucht sie bei der Initialisierung.
TEST_HOST = "mockhost"
TEST_PORT = 1234

# Diese Konstanten sollten auf Modulebene definiert sein
VALID_SUMMARY_RESPONSE = {
    "success": True,
    "data": {
        "summary": {
            "wwn1": {
                ATTR_DEVICE: {"device_name": "/dev/sda", "model_name": "DiskModelA"},
                ATTR_SMART: {"temp": 30},
            },
            "wwn2": {
                ATTR_DEVICE: {"device_name": "/dev/sdb", "model_name": "DiskModelB"},
                ATTR_SMART: {"temp": 35},
            },
        }
    },
}

VALID_DETAILS_RESPONSE_WWN1 = {
    "success": True,
    "data": {
        ATTR_DEVICE: {
            "device_name": "/dev/sda",
            "model_name": "DiskModelA",
            "capacity": 1000204886016,
        },
        ATTR_SMART_RESULTS: [
            {
                "attrs": {
                    "5": {"attribute_id": 5, "value": 100, "raw_value": 0},
                    "194": {"attribute_id": 194, "value": 30, "raw_value": 30},
                },
                "Status": 0,  # Overall SMART status
            }
        ],
    },
    ATTR_METADATA: {
        "5": {"display_name": "Reallocated Sectors Count"},
        "194": {"display_name": "Temperature Celsius"},
    },
}


# --- Erfolgsfall-Test für async_get_summary ---
@pytest.mark.asyncio
async def test_api_client_get_summary_success_mocking_request_method():
    """Test ScrutinyApiClient.async_get_summary success by mocking _request."""

    # Erstelle einen Mock für die ClientResponse, die _request zurückgeben würde
    mock_api_response = AsyncMock(spec=aiohttp.ClientResponse)
    mock_api_response.status = 200

    async def json_side_effect(*args, **kwargs):
        return VALID_SUMMARY_RESPONSE  # Greift auf die Modulebene-Konstante zu

    mock_api_response.json = AsyncMock(side_effect=json_side_effect)
    mock_api_response.headers = {"Content-Type": "application/json"}
    mock_api_response.raise_for_status = (
        AsyncMock()
    )  # Stellt sicher, dass kein HTTPError ausgelöst wird

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",  # Pfad zum Mocken
        return_value=mock_api_response,
    ) as mock_private_request:
        # Session ist hier nur ein Dummy, da _request gemockt ist
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )
            summary_data = await client.async_get_summary()

    # Überprüfe, ob _request korrekt aufgerufen wurde
    mock_private_request.assert_called_once_with("get", "summary")

    # Überprüfe das von async_get_summary verarbeitete Ergebnis
    assert summary_data is not None
    assert isinstance(summary_data, dict)
    assert "wwn1" in summary_data
    # Der Client gibt den Inhalt von response_json["data"]["summary"] zurück
    assert summary_data["wwn1"][ATTR_DEVICE]["model_name"] == "DiskModelA"
    assert summary_data["wwn2"][ATTR_SMART]["temp"] == 35

    print("SUCCESS: API client get_summary with _request mocked test passed!")


# --- Erfolgsfall-Test für async_get_device_details ---
@pytest.mark.asyncio
async def test_api_client_get_device_details_success_mocking_request_method():
    """Test ScrutinyApiClient.async_get_device_details success by mocking _request."""
    test_wwn = "wwn1_test_identifier"

    mock_api_response = AsyncMock(spec=aiohttp.ClientResponse)
    mock_api_response.status = 200

    async def json_side_effect(*args, **kwargs):
        return VALID_DETAILS_RESPONSE_WWN1  # Greift auf die Modulebene-Konstante zu

    mock_api_response.json = AsyncMock(side_effect=json_side_effect)
    mock_api_response.headers = {"Content-Type": "application/json"}
    mock_api_response.raise_for_status = AsyncMock()

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        return_value=mock_api_response,
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )
            details_data = await client.async_get_device_details(wwn=test_wwn)

    expected_endpoint = f"device/{test_wwn}/details"
    mock_private_request.assert_called_once_with("get", expected_endpoint)

    # Deine Methode gibt das gesamte erfolgreiche JSON-Antwortobjekt zurück
    assert details_data is not None
    assert isinstance(details_data, dict)
    assert details_data["success"] is True
    assert "data" in details_data
    assert ATTR_METADATA in details_data  # ATTR_METADATA ist 'metadata'
    assert details_data["data"][ATTR_DEVICE]["model_name"] == "DiskModelA"
    assert "5" in details_data[ATTR_METADATA]

    print("SUCCESS: API client get_device_details with _request mocked test passed!")


@pytest.mark.asyncio
async def test_api_client_get_summary_handles_connection_error():
    """Test ScrutinyApiClient.async_get_summary handles ScrutinyApiConnectionError from _request."""

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        new_callable=AsyncMock,
        # Simuliere, dass _request eine ScrutinyApiConnectionError wirft
        side_effect=ScrutinyApiConnectionError(
            "Simulated ScrutinyApiConnectionError from _request mock"
        ),
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiConnectionError) as excinfo:
                await client.async_get_summary()

            # Jetzt sollte die Nachricht der direkt geworfenen Exception entsprechen
            assert "Simulated ScrutinyApiConnectionError from _request mock" in str(
                excinfo.value
            )
            # Die URL-Konstruktion passiert in der echten _request, die wir hier komplett mocken,
            # also ist die URL nicht unbedingt Teil der Exception-Nachricht des Mocks.
            # Wenn du das testen willst, müsste der Mock komplexer sein.

        mock_private_request.assert_called_once_with("get", "summary")

    print(
        "SUCCESS: test_api_client_get_summary_handles_connection_error (simulating ScrutinyApiConnectionError) passed!"
    )


@pytest.mark.asyncio
async def test_api_client_get_summary_handles_auth_error():
    """Test ScrutinyApiClient.async_get_summary handles a 401/403 error from _request."""

    # Simuliere, dass _request eine ScrutinyApiAuthError wirft
    # (weil die echte _request eine aiohttp.ClientResponseError(status=401)
    # in eine ScrutinyApiAuthError umwandeln würde)
    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        new_callable=AsyncMock,
        side_effect=ScrutinyApiAuthError("Simulated 401 Auth Error from _request mock"),
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiAuthError) as excinfo:
                await client.async_get_summary()

            assert "Simulated 401 Auth Error" in str(excinfo.value)
            # Die URL-Konstruktion ist hier weniger relevant, da der Fehler
            # direkt vom _request-Mock kommt.

        mock_private_request.assert_called_once_with("get", "summary")

    print("SUCCESS: test_api_client_get_summary_handles_auth_error passed!")


@pytest.mark.asyncio
async def test_api_client_get_summary_handles_server_error():
    """Test ScrutinyApiClient.async_get_summary handles a 500 error from _request."""

    # Simuliere, dass _request eine ScrutinyApiResponseError wirft
    # (weil die echte _request eine aiohttp.ClientResponseError(status=500)
    # in eine ScrutinyApiResponseError umwandeln würde)
    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        new_callable=AsyncMock,
        side_effect=ScrutinyApiResponseError(
            "Simulated 500 Server Error from _request mock"
        ),
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiResponseError) as excinfo:
                await client.async_get_summary()

            assert "Simulated 500 Server Error" in str(excinfo.value)

        mock_private_request.assert_called_once_with("get", "summary")

    print("SUCCESS: test_api_client_get_summary_handles_server_error passed!")


@pytest.mark.asyncio
async def test_api_client_get_summary_handles_wrong_content_type():
    """Test ScrutinyApiClient.async_get_summary handles wrong content type."""

    mock_api_response = AsyncMock(spec=aiohttp.ClientResponse)
    mock_api_response.status = 200
    mock_api_response.headers = {"Content-Type": "text/html"}  # Falscher Content-Type

    # text() wird aufgerufen, wenn Content-Type nicht JSON ist
    async def text_side_effect(*args, **kwargs):
        return "This is HTML"

    mock_api_response.text = AsyncMock(side_effect=text_side_effect)
    mock_api_response.raise_for_status = AsyncMock()
    # .json() wird hier nicht direkt aufgerufen, da der Content-Type-Check vorher greift

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        return_value=mock_api_response,
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiResponseError) as excinfo:
                await client.async_get_summary()

            assert "Expected JSON from Scrutiny summary, got text/html" in str(
                excinfo.value
            )

        mock_private_request.assert_called_once_with("get", "summary")

    print("SUCCESS: test_api_client_get_summary_handles_wrong_content_type passed!")


# tests/test_api.py


@pytest.mark.asyncio
async def test_api_client_get_summary_handles_json_decode_error():
    """Test ScrutinyApiClient.async_get_summary handles JSONDecodeError."""

    mock_api_response = AsyncMock(spec=aiohttp.ClientResponse)
    mock_api_response.status = 200
    mock_api_response.headers = {"Content-Type": "application/json"}
    mock_api_response.json = AsyncMock(
        side_effect=json.JSONDecodeError("Simulated decode error", "doc", 0)
    )

    async def text_side_effect(*args, **kwargs):
        return "invalid json"

    mock_api_response.text = AsyncMock(side_effect=text_side_effect)
    mock_api_response.raise_for_status = AsyncMock()

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        return_value=mock_api_response,
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiResponseError) as excinfo:
                await client.async_get_summary()

            # Überprüfe nur die Hauptnachricht der ScrutinyApiResponseError
            assert "Invalid JSON response received from Scrutiny summary" in str(
                excinfo.value
            )
            # Entferne oder kommentiere die folgende Zeile aus:
            # assert "Simulated decode error" in str(excinfo.value)

            # Optional: Überprüfe die Ursache, wenn du das möchtest
            assert isinstance(excinfo.value.__cause__, json.JSONDecodeError)
            assert "Simulated decode error" in str(excinfo.value.__cause__)

        mock_private_request.assert_called_once_with("get", "summary")

    print("SUCCESS: test_api_client_get_summary_handles_json_decode_error passed!")


@pytest.mark.asyncio
async def test_api_client_get_device_details_handles_connection_error():
    """Test ScrutinyApiClient.async_get_device_details handles ScrutinyApiConnectionError from _request."""
    test_wwn = "wwn_for_conn_error_details_test"
    expected_endpoint = f"device/{test_wwn}/details"
    # Die URL, die in der Exception-Nachricht von _construct_api_exception_message erwartet wird
    expected_url_in_message = f"http://{TEST_HOST}:{TEST_PORT}/api/{expected_endpoint}"

    # Simuliere, dass _request eine ScrutinyApiConnectionError wirft
    # (weil die echte _request eine aiohttp.ClientConnectionError
    # in eine ScrutinyApiConnectionError umwandeln würde)
    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        new_callable=AsyncMock,
        side_effect=ScrutinyApiConnectionError(
            # Konstruiere die Nachricht so, wie es _construct_api_exception_message tun würde,
            # wenn _request die aiohttp.ClientConnectionError fängt.
            # Dies macht die Assertion der Exception-Nachricht präziser.
            f"Connection error with Scrutiny at {expected_url_in_message}: Simulated details connection error"
        ),
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiConnectionError) as excinfo:
                await client.async_get_device_details(wwn=test_wwn)

            # Überprüfe die Nachricht der ausgelösten Exception
            assert "Connection error with Scrutiny" in str(excinfo.value)
            assert "Simulated details connection error" in str(excinfo.value)
            assert expected_url_in_message in str(excinfo.value)

        # Stelle sicher, dass _request aufgerufen wurde, bevor die Exception geworfen wurde
        mock_private_request.assert_called_once_with("get", expected_endpoint)

    print(
        "SUCCESS: test_api_client_get_device_details_handles_connection_error passed!"
    )


@pytest.mark.asyncio
async def test_api_client_get_device_details_handles_auth_error():
    """Test ScrutinyApiClient.async_get_device_details handles a 401/403 error."""
    test_wwn = "wwn_auth_error_details"
    expected_endpoint = f"device/{test_wwn}/details"

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        new_callable=AsyncMock,
        side_effect=ScrutinyApiAuthError(
            f"Simulated 401 Auth Error for {expected_endpoint}"
        ),
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiAuthError) as excinfo:
                await client.async_get_device_details(wwn=test_wwn)

            assert f"Simulated 401 Auth Error for {expected_endpoint}" in str(
                excinfo.value
            )

        mock_private_request.assert_called_once_with("get", expected_endpoint)

    print("SUCCESS: test_api_client_get_device_details_handles_auth_error passed!")

    # tests/test_api.py


@pytest.mark.asyncio
async def test_api_client_get_device_details_handles_server_error():
    """Test ScrutinyApiClient.async_get_device_details handles a 500 error."""
    test_wwn = "wwn_server_error_details"
    expected_endpoint = f"device/{test_wwn}/details"

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        new_callable=AsyncMock,
        side_effect=ScrutinyApiResponseError(
            f"Simulated 500 Server Error for {expected_endpoint}"
        ),
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiResponseError) as excinfo:
                await client.async_get_device_details(wwn=test_wwn)

            assert f"Simulated 500 Server Error for {expected_endpoint}" in str(
                excinfo.value
            )

        mock_private_request.assert_called_once_with("get", expected_endpoint)

    print("SUCCESS: test_api_client_get_device_details_handles_server_error passed!")

    # tests/test_api.py


@pytest.mark.asyncio
async def test_api_client_get_device_details_handles_wrong_content_type():
    """Test ScrutinyApiClient.async_get_device_details handles wrong content type."""
    test_wwn = "wwn_wrong_content_details"
    expected_endpoint = f"device/{test_wwn}/details"

    mock_api_response = AsyncMock(spec=aiohttp.ClientResponse)
    mock_api_response.status = 200
    mock_api_response.headers = {"Content-Type": "text/plain"}  # Falscher Content-Type

    async def text_side_effect(*args, **kwargs):
        return "This is not JSON"

    mock_api_response.text = AsyncMock(
        side_effect=text_side_effect
    )  # Wird für Logging genutzt
    mock_api_response.raise_for_status = AsyncMock()

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        return_value=mock_api_response,
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiResponseError) as excinfo:
                await client.async_get_device_details(wwn=test_wwn)

            assert (
                f"Expected JSON from Scrutiny device details (WWN: {test_wwn}), got text/plain"
                in str(excinfo.value)
            )

        mock_private_request.assert_called_once_with("get", expected_endpoint)

    print(
        "SUCCESS: test_api_client_get_device_details_handles_wrong_content_type passed!"
    )


@pytest.mark.asyncio
async def test_api_client_get_device_details_handles_json_decode_error():
    """Test ScrutinyApiClient.async_get_device_details handles JSONDecodeError."""
    test_wwn = "wwn_json_decode_error_details"
    expected_endpoint = f"device/{test_wwn}/details"

    mock_api_response = AsyncMock(spec=aiohttp.ClientResponse)
    mock_api_response.status = 200
    mock_api_response.headers = {"Content-Type": "application/json"}
    mock_api_response.json = AsyncMock(
        side_effect=json.JSONDecodeError("Simulated details decode error", "doc", 0)
    )

    async def text_side_effect(*args, **kwargs):  # Für Logging im Fehlerfall
        return "invalid json content for details"

    mock_api_response.text = AsyncMock(side_effect=text_side_effect)
    mock_api_response.raise_for_status = AsyncMock()

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        return_value=mock_api_response,
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiResponseError) as excinfo:
                await client.async_get_device_details(wwn=test_wwn)

            assert (
                f"Invalid JSON response received from Scrutiny device details (WWN: {test_wwn})"
                in str(excinfo.value)
            )
            # Überprüfe die Ursache, wenn du die Original-Fehlermeldung brauchst
            assert isinstance(excinfo.value.__cause__, json.JSONDecodeError)
            assert "Simulated details decode error" in str(excinfo.value.__cause__)

        mock_private_request.assert_called_once_with("get", expected_endpoint)

    print(
        "SUCCESS: test_api_client_get_device_details_handles_json_decode_error passed!"
    )


@pytest.mark.asyncio
async def test_api_client_get_device_details_handles_success_false():
    """Test ScrutinyApiClient.async_get_device_details handles 'success: false'."""
    test_wwn = "wwn_success_false_details"
    expected_endpoint = f"device/{test_wwn}/details"
    faulty_response_json = {
        "success": False,
        "message": "API call failed for details",
        # data und metadata könnten hier fehlen oder vorhanden sein
    }

    mock_api_response = AsyncMock(spec=aiohttp.ClientResponse)
    mock_api_response.status = (
        200  # API antwortet erfolgreich, aber Inhalt signalisiert Fehler
    )
    mock_api_response.headers = {"Content-Type": "application/json"}

    async def json_side_effect(*args, **kwargs):
        return faulty_response_json

    mock_api_response.json = AsyncMock(side_effect=json_side_effect)
    mock_api_response.raise_for_status = AsyncMock()

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        return_value=mock_api_response,
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiResponseError) as excinfo:
                await client.async_get_device_details(wwn=test_wwn)

            assert (
                "Scrutiny API device details call not successful or unexpected format"
                in str(excinfo.value)
            )
            assert f"(WWN: {test_wwn})" in str(excinfo.value)

        mock_private_request.assert_called_once_with("get", expected_endpoint)

    print("SUCCESS: test_api_client_get_device_details_handles_success_false passed!")


@pytest.mark.asyncio
async def test_api_client_get_device_details_handles_missing_data_key():
    """Test ScrutinyApiClient.async_get_device_details handles missing 'data' key."""
    test_wwn = "wwn_missing_data_details"
    expected_endpoint = f"device/{test_wwn}/details"
    faulty_response_json = {
        "success": True,
        # "data": { ... }, // DATA FEHLT!
        ATTR_METADATA: {"some_meta_key": "some_meta_value"},
    }

    mock_api_response = AsyncMock(spec=aiohttp.ClientResponse)
    mock_api_response.status = 200
    mock_api_response.headers = {"Content-Type": "application/json"}

    async def json_side_effect(*args, **kwargs):
        return faulty_response_json

    mock_api_response.json = AsyncMock(side_effect=json_side_effect)
    mock_api_response.raise_for_status = AsyncMock()

    with patch(
        "custom_components.scrutiny.api.ScrutinyApiClient._request",
        return_value=mock_api_response,
    ) as mock_private_request:
        async with aiohttp.ClientSession() as dummy_session:
            client = ScrutinyApiClient(
                host=TEST_HOST, port=TEST_PORT, session=dummy_session
            )

            with pytest.raises(ScrutinyApiResponseError) as excinfo:
                await client.async_get_device_details(wwn=test_wwn)

            assert "response is missing 'data' or 'metadata' key" in str(excinfo.value)
            assert f"(WWN: {test_wwn})" in str(excinfo.value)

        mock_private_request.assert_called_once_with("get", expected_endpoint)

    print(
        "SUCCESS: test_api_client_get_device_details_handles_missing_data_key passed!"
    )
