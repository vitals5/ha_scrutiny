import pytest
from unittest.mock import patch, AsyncMock, MagicMock  # MagicMock für komplexere Mocks

import asyncio  # Für asyncio.gather Simulation

from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.core import (
    HomeAssistant,
)  # Für Type Hinting, wird von Fixture bereitgestellt

# Zu testende Klasse und Exceptions
from custom_components.scrutiny.coordinator import ScrutinyDataUpdateCoordinator
from custom_components.scrutiny.api import (
    ScrutinyApiClient,  # Wird gemockt
    ScrutinyApiConnectionError,
    ScrutinyApiResponseError,
    # ScrutinyApiAuthError, # Je nachdem, ob wir es testen wollen
)

# Konstanten, die der Koordinator verwendet
from custom_components.scrutiny.const import (
    LOGGER,  # Kann auch gemockt werden
    DOMAIN,
    ATTR_DEVICE,
    ATTR_SMART,
    ATTR_METADATA,
    ATTR_SMART_RESULTS,
    KEY_SUMMARY_DEVICE,
    KEY_SUMMARY_SMART,
    KEY_DETAILS_DEVICE,
    KEY_DETAILS_SMART_LATEST,
    KEY_DETAILS_METADATA,
)

from datetime import timedelta

# Konstanten für Kapazitätsberechnung ZUERST definieren
TB_IN_BYTES = 1024 * 1024 * 1024 * 1024  # 1 Terabyte in Bytes

# Was api_client.async_get_summary() zurückgibt
MOCK_API_SUMMARY_DATA = {
    "wwn1": {
        ATTR_DEVICE: {"device_name": "/dev/sda", "model_name": "DiskModelA_Sum"},
        ATTR_SMART: {"temp": 30, "power_on_hours": 1000},
    },
    "wwn2": {
        ATTR_DEVICE: {"device_name": "/dev/sdb", "model_name": "DiskModelB_Sum"},
        ATTR_SMART: {"temp": 35, "power_on_hours": 2000},
    },
}

# Was api_client.async_get_device_details("wwn1") zurückgibt
MOCK_API_DETAILS_DATA_WWN1 = {
    "success": True,
    "data": {
        ATTR_DEVICE: {
            "device_name": "/dev/sda",
            "model_name": "DiskModelA_Det",
            "capacity": 1 * TB_IN_BYTES,  # Verwende die definierte Konstante
        },
        ATTR_SMART_RESULTS: [
            {
                "attrs": {"5": {"attribute_id": 5, "value": 100}},
                "Status": 0,
                "temp": 31,
                "power_on_hours": 1001,
            }
        ],
    },
    ATTR_METADATA: {"5": {"display_name": "Reallocated Sectors Count"}},
}

# Was api_client.async_get_device_details("wwn2") zurückgibt
MOCK_API_DETAILS_DATA_WWN2 = {
    "success": True,
    "data": {
        ATTR_DEVICE: {
            "device_name": "/dev/sdb",
            "model_name": "DiskModelB_Det",
            "capacity": 2 * TB_IN_BYTES,  # Verwende die definierte Konstante
        },
        ATTR_SMART_RESULTS: [
            {
                "attrs": {"194": {"attribute_id": 194, "value": 36}},
                "Status": 0,
                "temp": 36,
                "power_on_hours": 2002,
            }
        ],
    },
    ATTR_METADATA: {"194": {"display_name": "Temperature Celsius"}},
}


# --- Hilfsfunktion zum Erstellen eines Koordinator-Mocks ---
async def create_mocked_coordinator(
    hass: HomeAssistant,  # Wird von pytest-homeassistant-custom-component bereitgestellt
    mock_api_client: AsyncMock,  # Ein bereits konfigurierter Mock für ScrutinyApiClient
) -> ScrutinyDataUpdateCoordinator:
    """Helper to create a ScrutinyDataUpdateCoordinator with a mocked API client."""
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,  # Du könntest hier auch einen MagicMock() für den Logger übergeben
        name=f"{DOMAIN}-test-coordinator",
        api_client=mock_api_client,
        update_interval=timedelta(
            seconds=30
        ),  # Irrelevant für manuelle Updates im Test
    )
    return coordinator


@pytest.mark.asyncio
async def test_coordinator_async_update_data_success(hass: HomeAssistant):
    # ... (Mock-Setup bleibt gleich) ...
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    mock_api_client.async_get_summary = AsyncMock(return_value=MOCK_API_SUMMARY_DATA)

    async def mock_details_side_effect(wwn):
        if wwn == "wwn1":
            return MOCK_API_DETAILS_DATA_WWN1
        if wwn == "wwn2":
            return MOCK_API_DETAILS_DATA_WWN2
        return {}

    mock_api_client.async_get_device_details = AsyncMock(
        side_effect=mock_details_side_effect
    )

    coordinator = await create_mocked_coordinator(hass, mock_api_client)

    # 4. Führe die zu testende Methode aus -> Verwende async_refresh()
    # updated_data = await coordinator._async_update_data() # Alte Methode
    await (
        coordinator.async_refresh()
    )  # NEUE METHODE: Löst Update aus und setzt coordinator.data

    # Die Daten sollten jetzt in coordinator.data sein
    updated_data = coordinator.data  # Hole die Daten aus der Instanzvariable

    # 5. Überprüfe die Aufrufe am Mock-API-Client (bleibt gleich)
    mock_api_client.async_get_summary.assert_called_once()
    assert mock_api_client.async_get_device_details.call_count == len(
        MOCK_API_SUMMARY_DATA
    )
    mock_api_client.async_get_device_details.assert_any_call("wwn1")
    mock_api_client.async_get_device_details.assert_any_call("wwn2")

    # 6. Überprüfe die Struktur und den Inhalt der aggregierten Daten (bleibt gleich)
    assert updated_data is not None
    assert "wwn1" in updated_data
    # ... (Rest der Assertions für updated_data) ...

    # Die letzte Assertion ist jetzt implizit, da updated_data = coordinator.data ist
    # assert coordinator.data == updated_data # Diese Zeile ist jetzt nicht mehr nötig oder kann so bleiben

    print("SUCCESS: test_coordinator_async_update_data_success passed!")


@pytest.mark.asyncio
async def test_coordinator_update_fails_on_summary_connection_error(
    hass: HomeAssistant,
):
    """Test coordinator handles summary connection error and sets last_update_success to False."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    mock_api_client.async_get_summary = AsyncMock(
        side_effect=ScrutinyApiConnectionError("Simulated summary connection error")
    )
    mock_api_client.async_get_device_details = AsyncMock()

    coordinator = await create_mocked_coordinator(hass, mock_api_client)

    # Führe async_refresh aus. Wir erwarten jetzt NICHT unbedingt, dass es UpdateFailed wirft,
    # sondern dass es den Fehler intern behandelt.
    # Die DataUpdateCoordinator-Basisklasse fängt die Exception von _async_update_data
    # (wenn es nicht UpdateFailed ist) oder die UpdateFailed selbst.
    # Sie loggt den Fehler und setzt last_update_success.

    # Wir müssen prüfen, ob async_refresh selbst eine Exception wirft,
    # die nicht UpdateFailed ist, was nicht passieren sollte.
    # Wenn _async_update_data UpdateFailed wirft, wird async_refresh es fangen und nicht weiterwerfen.
    # Wenn _async_update_data eine andere Exception wirft, wird async_refresh diese fangen und nicht weiterwerfen.

    # Versuche, den Refresh auszuführen. Er sollte keine Exception an den Test weitergeben.
    await coordinator.async_refresh()

    # Überprüfe den Status nach dem fehlgeschlagenen Refresh
    assert coordinator.last_update_success is False  # <--- NEUE HAUPT-ASSERTION

    # Die ursprüngliche Exception sollte im Koordinator als self.last_exception gespeichert sein
    # (oder zumindest die UpdateFailed, die von _raise_update_failed geworfen wurde)
    assert coordinator.last_exception is not None
    # Überprüfe den Typ der gespeicherten Exception.
    # Wenn dein _async_update_data UpdateFailed wirft, sollte es hier UpdateFailed sein.
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert "Connection error during Scrutiny data update cycle" in str(
        coordinator.last_exception
    )
    assert "Simulated summary connection error" in str(coordinator.last_exception)

    # Überprüfe die Mock-Aufrufe
    mock_api_client.async_get_summary.assert_called_once()
    mock_api_client.async_get_device_details.assert_not_called()

    # coordinator.data sollte nach einem fehlgeschlagenen ersten Update None sein
    assert coordinator.data is None

    print(
        "SUCCESS: test_coordinator_update_fails_on_summary_connection_error (checking last_update_success) passed!"
    )


@pytest.mark.asyncio
async def test_coordinator_handles_partial_detail_failure(hass: HomeAssistant):
    """Test coordinator handles failure for one disk's details but processes others."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)

    # Summary ist erfolgreich
    mock_api_client.async_get_summary = AsyncMock(return_value=MOCK_API_SUMMARY_DATA)

    # Details für wwn1 ist erfolgreich, für wwn2 schlägt es fehl
    async def mock_details_side_effect_with_failure(wwn):
        if wwn == "wwn1":
            return MOCK_API_DETAILS_DATA_WWN1
        if wwn == "wwn2":
            # Simuliere einen Fehler, den _process_detail_results als Exception erhält
            raise ScrutinyApiResponseError(
                "Simulated detail API response error for wwn2"
            )
        return {}  # Fallback, sollte nicht erreicht werden bei nur zwei WWNs

    mock_api_client.async_get_device_details = AsyncMock(
        side_effect=mock_details_side_effect_with_failure
    )

    coordinator = await create_mocked_coordinator(hass, mock_api_client)

    # async_refresh sollte hier KEINE UpdateFailed Exception werfen.
    # Der Fehler wird in _process_detail_results behandelt.
    await coordinator.async_refresh()

    updated_data = coordinator.data
    assert updated_data is not None
    assert coordinator.last_update_success is True  # Der Gesamt-Update war erfolgreich

    # Überprüfe Aufrufe
    mock_api_client.async_get_summary.assert_called_once()
    assert mock_api_client.async_get_device_details.call_count == len(
        MOCK_API_SUMMARY_DATA
    )
    mock_api_client.async_get_device_details.assert_any_call("wwn1")
    mock_api_client.async_get_device_details.assert_any_call("wwn2")

    # Daten für wwn1 sollten komplett sein
    assert "wwn1" in updated_data
    assert updated_data["wwn1"][KEY_SUMMARY_DEVICE]["model_name"] == "DiskModelA_Sum"
    assert updated_data["wwn1"][KEY_DETAILS_DEVICE]["model_name"] == "DiskModelA_Det"
    assert (
        updated_data["wwn1"][KEY_DETAILS_SMART_LATEST]["temp"] == 31
    )  # Aus MOCK_API_DETAILS_DATA_WWN1

    # Daten für wwn2: Summary sollte da sein, Details sollten leer sein
    # (gemäß deiner _process_detail_results Logik, die bei Exception leere Dicts setzt)
    assert "wwn2" in updated_data
    assert updated_data["wwn2"][KEY_SUMMARY_DEVICE]["model_name"] == "DiskModelB_Sum"
    assert updated_data["wwn2"][KEY_DETAILS_DEVICE] == {}
    assert updated_data["wwn2"][KEY_DETAILS_SMART_LATEST] == {}
    assert updated_data["wwn2"][KEY_DETAILS_METADATA] == {}

    print("SUCCESS: test_coordinator_handles_partial_detail_failure passed!")


@pytest.mark.asyncio  # Nicht unbedingt async, wenn _process_detail_results nicht async ist
async def test_process_detail_results_handles_exception_input(hass: HomeAssistant):
    """Test _process_detail_results correctly handles an Exception as input."""
    # Erstelle einen Dummy-Koordinator nur für diesen Test der Methode
    # Der API-Client-Mock ist hier nicht unbedingt nötig, wenn _process_detail_results ihn nicht direkt verwendet.
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name="test",
        api_client=mock_api_client,
        update_interval=timedelta(seconds=30),
    )

    wwn_key = "test_wwn_exception"
    # Simuliere, dass asyncio.gather eine Exception für diesen Task zurückgegeben hat
    exception_input = ValueError("Simulated error during detail fetch")
    target_data_dict = {}  # Das Dictionary, das die Methode befüllen soll

    # Rufe die Methode direkt auf
    coordinator._process_detail_results(wwn_key, exception_input, target_data_dict)

    # Überprüfe, ob die Detail-Keys mit leeren Dictionaries befüllt wurden
    assert target_data_dict[KEY_DETAILS_DEVICE] == {}
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}
    assert target_data_dict[KEY_DETAILS_METADATA] == {}
    # Optional: Überprüfe, ob eine Warnung geloggt wurde (erfordert Mocking des Loggers)


@pytest.mark.asyncio
async def test_process_detail_results_handles_valid_input(hass: HomeAssistant):
    """Test _process_detail_results correctly handles valid detail input."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    coordinator = ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name="test",
        api_client=mock_api_client,
        update_interval=timedelta(seconds=30),
    )
    wwn_key = "wwn1"
    # Verwende unsere MOCK_API_DETAILS_DATA_WWN1 als valide Eingabe
    valid_input = MOCK_API_DETAILS_DATA_WWN1
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, valid_input, target_data_dict)

    assert (
        target_data_dict[KEY_DETAILS_DEVICE]
        == MOCK_API_DETAILS_DATA_WWN1["data"][ATTR_DEVICE]
    )
    assert (
        target_data_dict[KEY_DETAILS_SMART_LATEST]
        == MOCK_API_DETAILS_DATA_WWN1["data"][ATTR_SMART_RESULTS][0]
    )
    assert (
        target_data_dict[KEY_DETAILS_METADATA]
        == MOCK_API_DETAILS_DATA_WWN1[ATTR_METADATA]
    )


@pytest.mark.asyncio
async def test_coordinator_handles_empty_summary(hass: HomeAssistant):
    """Test coordinator handles an empty summary (no disks)."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    mock_api_client.async_get_summary = AsyncMock(return_value={})  # Leeres Summary
    mock_api_client.async_get_device_details = AsyncMock()

    coordinator = await create_mocked_coordinator(hass, mock_api_client)
    await coordinator.async_refresh()

    assert coordinator.data == {}
    assert coordinator.last_update_success is True
    mock_api_client.async_get_summary.assert_called_once()
    mock_api_client.async_get_device_details.assert_not_called()  # Wichtig!


@pytest.mark.asyncio
async def test_coordinator_handles_invalid_summary_type(hass: HomeAssistant):
    """Test coordinator handles summary data that is not a dictionary and sets last_update_success."""
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    mock_api_client.async_get_summary = AsyncMock(
        return_value="not a dict"  # Ungültiger Typ
    )
    mock_api_client.async_get_device_details = AsyncMock()

    coordinator = await create_mocked_coordinator(hass, mock_api_client)

    # Führe async_refresh aus. Er sollte den Fehler intern behandeln.
    await coordinator.async_refresh()

    # Überprüfe den Status nach dem fehlgeschlagenen Refresh
    assert coordinator.last_update_success is False

    assert coordinator.last_exception is not None
    assert isinstance(coordinator.last_exception, UpdateFailed)

    # Die Nachricht von UpdateFailed wird von _raise_update_failed im Koordinator konstruiert.
    # Sie enthält die Nachricht des ScrutinyApiError, der die ScrutinyApiResponseError war.
    # Die ursprüngliche ScrutinyApiResponseError hatte die Nachricht "Summary data from API was not a dictionary."
    # Der ScrutinyApiError-Block macht daraus:
    # f"API error during Scrutiny data update cycle: {err!s}"
    # wobei err!s dann "Summary data from API was not a dictionary." ist.

    # Erwartete Nachricht in last_exception.args[0] oder str(coordinator.last_exception)
    expected_msg_part_from_api_error = "Summary data from API was not a dictionary."
    expected_wrapper_msg = "API error during Scrutiny data update cycle"

    assert expected_wrapper_msg in str(coordinator.last_exception)
    assert expected_msg_part_from_api_error in str(coordinator.last_exception)

    # Überprüfe die Ursache der UpdateFailed-Exception, es sollte die ScrutinyApiResponseError sein
    assert isinstance(coordinator.last_exception.__cause__, ScrutinyApiResponseError)
    assert expected_msg_part_from_api_error in str(coordinator.last_exception.__cause__)

    # Überprüfe Mock-Aufrufe
    mock_api_client.async_get_summary.assert_called_once()
    mock_api_client.async_get_device_details.assert_not_called()

    assert coordinator.data is None  # Da der erste Refresh fehlschlug

    print(
        "SUCCESS: test_coordinator_handles_invalid_summary_type (checking last_update_success) passed!"
    )


# --- Tests für _process_detail_results ---


def _get_dummy_coordinator_for_method_test(
    hass: HomeAssistant,
) -> ScrutinyDataUpdateCoordinator:
    """Helper to get a coordinator instance for testing its methods directly."""
    # Der API-Client-Mock ist hier oft nicht kritisch, da _process_detail_results
    # ihn normalerweise nicht direkt verwendet, sondern nur die Daten, die er geliefert hätte.
    mock_api_client = AsyncMock(spec=ScrutinyApiClient)
    return ScrutinyDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,  # Oder ein MagicMock() für den Logger, um Log-Ausgaben zu prüfen
        name="test_process_details",
        api_client=mock_api_client,
        update_interval=timedelta(seconds=30),
    )


# --- Tests für die Methode _process_detail_results ---


def test_process_detail_results_with_valid_data(hass: HomeAssistant):
    """Test _process_detail_results with a valid full_detail_response dictionary."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn1_valid"
    # Erstelle eine tiefe Kopie, um Seiteneffekte zu vermeiden, wenn MOCK_API_DETAILS_DATA_WWN1 global ist
    # und in anderen Tests modifiziert werden könnte (hier nicht der Fall, aber gute Praxis).
    # import copy; valid_input = copy.deepcopy(MOCK_API_DETAILS_DATA_WWN1)
    valid_input = MOCK_API_DETAILS_DATA_WWN1
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, valid_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == valid_input["data"][ATTR_DEVICE]
    assert (
        target_data_dict[KEY_DETAILS_SMART_LATEST]
        == valid_input["data"][ATTR_SMART_RESULTS][0]
    )
    assert target_data_dict[KEY_DETAILS_METADATA] == valid_input[ATTR_METADATA]
    print(f"SUCCESS: {test_process_detail_results_with_valid_data.__name__} passed!")


def test_process_detail_results_with_exception_input(hass: HomeAssistant, caplog):
    """Test _process_detail_results when full_detail_response is an Exception."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_ex_input"
    exception_input = ValueError("Simulated error from asyncio.gather for details")
    target_data_dict = {}

    # Optional: Teste, ob eine Warnung geloggt wird
    # caplog Fixture von pytest fängt Log-Ausgaben
    # import logging; caplog.set_level(logging.WARNING) # Stelle sicher, dass WARNINGS gefangen werden

    coordinator._process_detail_results(wwn_key, exception_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == {}
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}
    assert target_data_dict[KEY_DETAILS_METADATA] == {}

    # Optional: Überprüfe die Log-Ausgabe
    # assert f"Failed to fetch details for disk {wwn_key}" in caplog.text
    # assert str(exception_input) in caplog.text
    print(
        f"SUCCESS: {test_process_detail_results_with_exception_input.__name__} passed!"
    )


def test_process_detail_results_missing_data_key_in_payload(hass: HomeAssistant):
    """Test _process_detail_results with missing 'data' key in the response payload."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_no_data_key"
    faulty_input = {  # 'data'-Schlüssel fehlt auf oberster Ebene
        "success": True,
        # "data": { ... } # FEHLT!
        ATTR_METADATA: {"1": {"display_name": "Test Attr"}},
    }
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, faulty_input, target_data_dict)

    # Erwartet leere Dicts, da 'data' fehlt, um 'device' und 'smart_results' zu extrahieren
    assert target_data_dict[KEY_DETAILS_DEVICE] == {}
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}
    # Metadaten sind auf oberster Ebene und sollten trotzdem extrahiert werden
    assert target_data_dict[KEY_DETAILS_METADATA] == faulty_input[ATTR_METADATA]
    print(
        f"SUCCESS: {test_process_detail_results_missing_data_key_in_payload.__name__} passed!"
    )


def test_process_detail_results_missing_smart_results_in_data(hass: HomeAssistant):
    """Test _process_detail_results with missing 'smart_results' within the 'data' payload."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_no_smart_results"
    faulty_input = {
        "success": True,
        "data": {
            ATTR_DEVICE: {"model_name": "TestDiskWithNoSmart"},
            # ATTR_SMART_RESULTS fehlt hier im 'data'-Objekt!
        },
        ATTR_METADATA: {"1": {"display_name": "Test Attr"}},
    }
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, faulty_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == faulty_input["data"][ATTR_DEVICE]
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}  # Sollte leer sein
    assert target_data_dict[KEY_DETAILS_METADATA] == faulty_input[ATTR_METADATA]
    print(
        f"SUCCESS: {test_process_detail_results_missing_smart_results_in_data.__name__} passed!"
    )


def test_process_detail_results_empty_smart_results_list(hass: HomeAssistant):
    """Test _process_detail_results with an empty 'smart_results' list."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_empty_smart_list"
    faulty_input = {
        "success": True,
        "data": {
            ATTR_DEVICE: {"model_name": "TestDiskEmptySmart"},
            ATTR_SMART_RESULTS: [],  # Leere Liste!
        },
        ATTR_METADATA: {"1": {"display_name": "Test Attr"}},
    }
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, faulty_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == faulty_input["data"][ATTR_DEVICE]
    assert target_data_dict[KEY_DETAILS_SMART_LATEST] == {}  # Sollte leer sein
    assert target_data_dict[KEY_DETAILS_METADATA] == faulty_input[ATTR_METADATA]
    print(
        f"SUCCESS: {test_process_detail_results_empty_smart_results_list.__name__} passed!"
    )


def test_process_detail_results_missing_metadata_key_in_payload(hass: HomeAssistant):
    """Test _process_detail_results with missing 'metadata' key in the response payload."""
    coordinator = _get_dummy_coordinator_for_method_test(hass)
    wwn_key = "wwn_no_metadata"
    faulty_input = {
        "success": True,
        "data": {
            ATTR_DEVICE: {"model_name": "TestDiskNoMetadata"},
            ATTR_SMART_RESULTS: [
                {"attrs": {}, "Status": 0}
            ],  # Gültige, aber leere Smart-Results
        },
        # ATTR_METADATA fehlt!
    }
    target_data_dict = {}

    coordinator._process_detail_results(wwn_key, faulty_input, target_data_dict)

    assert target_data_dict[KEY_DETAILS_DEVICE] == faulty_input["data"][ATTR_DEVICE]
    assert (
        target_data_dict[KEY_DETAILS_SMART_LATEST]
        == faulty_input["data"][ATTR_SMART_RESULTS][0]
    )
    assert target_data_dict[KEY_DETAILS_METADATA] == {}  # Sollte leer sein
    print(
        f"SUCCESS: {test_process_detail_results_missing_metadata_key_in_payload.__name__} passed!"
    )
