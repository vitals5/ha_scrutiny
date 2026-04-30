"""
Minimal but accurate stubs for the Home Assistant classes used by this integration.

These are NOT mocks — they implement just enough of the real HA API surface to
let our code run correctly under plain Python without a full HA installation.
Each stub matches the constructor signature and attribute names the integration
actually uses.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConfigEntryNotReady(Exception):
    pass


class UpdateFailed(Exception):
    pass


# ---------------------------------------------------------------------------
# homeassistant.core
# ---------------------------------------------------------------------------


class HomeAssistant:
    def __init__(self) -> None:
        self.config_entries = ConfigEntriesStub()
        self.data: dict = {}

    def async_create_task(self, coro):
        return asyncio.get_event_loop().create_task(coro)


class ConfigEntriesStub:
    def __init__(self) -> None:
        self._entries: dict[str, Any] = {}

    async def async_forward_entry_setups(self, entry, platforms):
        pass

    async def async_unload_platforms(self, entry, platforms):
        return True

    async def async_reload(self, entry_id):
        pass


# ---------------------------------------------------------------------------
# homeassistant.config_entries
# ---------------------------------------------------------------------------


class ConfigEntry:
    """Minimal config entry — covers all attributes the integration accesses."""

    def __init__(
        self,
        entry_id: str = "test_entry_id",
        data: dict | None = None,
        options: dict | None = None,
        title: str = "Test Entry",
    ) -> None:
        self.entry_id = entry_id
        self.data: dict = data or {}
        self.options: dict = options or {}
        self.runtime_data: Any = None
        self.title = title
        self._unload_listeners: list = []

    def async_on_unload(self, func):
        self._unload_listeners.append(func)
        return func

    def add_update_listener(self, func):
        self._unload_listeners.append(func)
        return func


class OptionsFlow:
    """Stub OptionsFlow base class."""

    def async_show_form(self, *, step_id: str, data_schema=None, errors=None) -> dict:
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def async_create_entry(self, *, title: str = "", data: dict) -> dict:
        return {"type": "create_entry", "title": title, "data": data}

    def async_abort(self, *, reason: str) -> dict:
        return {"type": "abort", "reason": reason}


class ConfigFlow:
    """Stub ConfigFlow base class."""

    VERSION = 1
    _flow_id: str = "test_flow"

    def __init_subclass__(cls, domain: str = "", **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        original_init = cls.__dict__.get("__init__")

        def patched_init(self, *args, **kw):
            self.hass = HomeAssistant()
            self.context: dict = {"entry_id": "test_entry_id"}
            if original_init:
                original_init(self, *args, **kw)

        cls.__init__ = patched_init

    async def async_set_unique_id(self, unique_id: str) -> None:
        self._unique_id = unique_id

    def _abort_if_unique_id_configured(self) -> None:
        pass

    def async_create_entry(
        self, *, title: str, data: dict, options: dict | None = None
    ) -> dict:
        return {
            "type": "create_entry",
            "title": title,
            "data": data,
            "options": options or {},
        }

    def async_show_form(self, *, step_id: str, data_schema=None, errors=None) -> dict:
        return {"type": "form", "step_id": step_id, "errors": errors or {}}

    def async_abort(self, *, reason: str) -> dict:
        return {"type": "abort", "reason": reason}


# ---------------------------------------------------------------------------
# homeassistant.helpers.update_coordinator
# ---------------------------------------------------------------------------


class DataUpdateCoordinator:
    """Minimal coordinator stub matching the constructor signature our code uses."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(
        self,
        hass: HomeAssistant,
        logger,
        *,
        name: str,
        update_interval: timedelta,
        config_entry=None,
    ) -> None:
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.config_entry = config_entry
        self.data: Any = None
        self.last_update_success: bool = True
        self.last_exception: Exception | None = None
        self._listeners: list = []

    async def async_config_entry_first_refresh(self) -> None:
        try:
            self.data = await self._async_update_data()
            self.last_update_success = True
        except UpdateFailed as err:
            self.last_exception = err
            self.last_update_success = False
            raise

    async def async_refresh(self) -> None:
        try:
            self.data = await self._async_update_data()
            self.last_update_success = True
            self.last_exception = None
        except UpdateFailed as err:
            self.last_exception = err
            self.last_update_success = False

    async def async_request_refresh(self) -> None:
        """Stub: trigger a refresh (no-op in tests unless overridden)."""
        pass

    async def _async_update_data(self) -> Any:
        raise NotImplementedError

    def async_add_listener(self, listener) -> callable:
        self._listeners.append(listener)

        def remove():
            self._listeners.remove(listener)

        return remove


class CoordinatorEntity:
    def __class_getitem__(cls, item):
        return cls

    """Stub CoordinatorEntity — our entities inherit from this."""
    _attr_unique_id: str | None = None
    _attr_name: str | None = None
    _attr_has_entity_name: bool = False
    _attr_entity_category = None
    _attr_entity_registry_enabled_default: bool = True
    _attr_native_unit_of_measurement: str | None = None
    _attr_device_class = None
    _attr_state_class = None
    _attr_native_value: Any = {}
    _attr_extra_state_attributes: dict = {}
    _attr_device_info: Any = None

    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        self.coordinator = coordinator

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def device_info(self):
        return self._attr_device_info

    @property
    def native_value(self):
        return self._attr_native_value

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def has_entity_name(self):
        return self._attr_has_entity_name

    @property
    def native_unit_of_measurement(self):
        return self._attr_native_unit_of_measurement

    @property
    def device_class(self):
        return self._attr_device_class

    def async_write_ha_state(self) -> None:
        pass  # no-op in tests


# ---------------------------------------------------------------------------
# homeassistant.helpers.device_registry
# ---------------------------------------------------------------------------


class DeviceEntryType:
    SERVICE = "service"


class DeviceEntry:
    def __init__(
        self, id: str, identifiers: set, config_entry_id: str, name: str = ""
    ) -> None:
        self.id = id
        self.identifiers = identifiers
        self.config_entry_id = config_entry_id
        self.name = name


class DeviceRegistry:
    def __init__(self) -> None:
        self._devices: dict[str, DeviceEntry] = {}
        self._by_config_entry: dict[str, list[DeviceEntry]] = {}
        self._created: list[dict] = []
        self._removed: list[str] = []

    def async_get_or_create(
        self,
        *,
        config_entry_id,
        identifiers,
        name="",
        manufacturer=None,
        model=None,
        configuration_url=None,
        via_device=None,
        entry_type=None,
        sw_version=None,
        serial_number=None,
    ) -> DeviceEntry:
        key = frozenset(identifiers)
        for dev in self._devices.values():
            if frozenset(dev.identifiers) == key:
                return dev
        dev_id = f"dev_{len(self._devices)}"
        entry = DeviceEntry(dev_id, identifiers, config_entry_id, name)
        self._devices[dev_id] = entry
        self._by_config_entry.setdefault(config_entry_id, []).append(entry)
        self._created.append({"name": name, "identifiers": identifiers})
        return entry

    def async_remove_device(self, device_id: str) -> None:
        dev = self._devices.pop(device_id, None)
        if dev:
            self._removed.append(device_id)
            entries = self._by_config_entry.get(dev.config_entry_id, [])
            if dev in entries:
                entries.remove(dev)

    def async_entries_for_config_entry(self, config_entry_id: str) -> list[DeviceEntry]:
        return list(self._by_config_entry.get(config_entry_id, []))


_DEVICE_REGISTRY: DeviceRegistry | None = None


def async_get(hass) -> DeviceRegistry:
    global _DEVICE_REGISTRY
    if _DEVICE_REGISTRY is None:
        _DEVICE_REGISTRY = DeviceRegistry()
    return _DEVICE_REGISTRY


def async_entries_for_config_entry(
    registry: DeviceRegistry, entry_id: str
) -> list[DeviceEntry]:
    return registry.async_entries_for_config_entry(entry_id)


def reset_registry() -> None:
    global _DEVICE_REGISTRY
    _DEVICE_REGISTRY = None


# ---------------------------------------------------------------------------
# homeassistant.helpers.entity_registry
# ---------------------------------------------------------------------------


class EntityEntry:
    def __init__(self, entity_id: str, unique_id: str, config_entry_id: str) -> None:
        self.entity_id = entity_id
        self.unique_id = unique_id
        self.config_entry_id = config_entry_id


class EntityRegistry:
    def __init__(self) -> None:
        self._entities: dict[str, EntityEntry] = {}
        self._by_config_entry: dict[str, list[EntityEntry]] = {}
        self._removed: list[str] = []

    def async_get_or_create(
        self, *, config_entry_id: str, platform: str, unique_id: str, **kwargs
    ) -> EntityEntry:
        for ent in self._entities.values():
            if ent.unique_id == unique_id and ent.config_entry_id == config_entry_id:
                return ent
        entity_id = f"{platform}.{unique_id.replace(' ', '_')}"
        entry = EntityEntry(entity_id, unique_id, config_entry_id)
        self._entities[entity_id] = entry
        self._by_config_entry.setdefault(config_entry_id, []).append(entry)
        return entry

    def async_remove(self, entity_id: str) -> None:
        ent = self._entities.pop(entity_id, None)
        if ent:
            self._removed.append(entity_id)
            entries = self._by_config_entry.get(ent.config_entry_id, [])
            if ent in entries:
                entries.remove(ent)

    def async_entries_for_config_entry(self, config_entry_id: str) -> list[EntityEntry]:
        return list(self._by_config_entry.get(config_entry_id, []))


_ENTITY_REGISTRY: EntityRegistry | None = None


def er_async_get(hass) -> EntityRegistry:
    global _ENTITY_REGISTRY
    if _ENTITY_REGISTRY is None:
        _ENTITY_REGISTRY = EntityRegistry()
    return _ENTITY_REGISTRY


def er_async_entries_for_config_entry(
    registry: EntityRegistry, entry_id: str
) -> list[EntityEntry]:
    return registry.async_entries_for_config_entry(entry_id)


def reset_entity_registry() -> None:
    global _ENTITY_REGISTRY
    _ENTITY_REGISTRY = None


# ---------------------------------------------------------------------------
# homeassistant.helpers.entity (DeviceInfo is a TypedDict in real HA)
# ---------------------------------------------------------------------------


class DeviceInfo(dict):
    pass


# ---------------------------------------------------------------------------
# homeassistant.components.sensor
# ---------------------------------------------------------------------------


class SensorStateClass:
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


class SensorDeviceClass:
    TEMPERATURE = "temperature"
    DURATION = "duration"
    ENUM = "enum"
    TIMESTAMP = "timestamp"
    DATA_SIZE = "data_size"


class SensorEntityDescription:
    """Matches the real HA SensorEntityDescription dataclass fields we use."""

    def __init__(
        self,
        key: str = "",
        translation_key: str | None = None,
        name: str | None = None,
        native_unit_of_measurement: str | None = None,
        device_class: str | None = None,
        state_class: str | None = None,
        entity_category=None,
        suggested_unit_of_measurement: str | None = None,
        suggested_display_precision: int | None = None,
        options: list | None = None,
        icon: str | None = None,
    ) -> None:
        self.key = key
        self.translation_key = translation_key
        self.name = name
        self.native_unit_of_measurement = native_unit_of_measurement
        self.device_class = device_class
        self.state_class = state_class
        self.entity_category = entity_category
        self.suggested_unit_of_measurement = suggested_unit_of_measurement
        self.suggested_display_precision = suggested_display_precision
        self.options = options
        self.icon = icon


class SensorEntity:
    """Platform base — does NOT inherit CoordinatorEntity to avoid MRO conflicts."""

    @property
    def native_value(self):
        return None

    @property
    def extra_state_attributes(self):
        return {}


# ---------------------------------------------------------------------------
# homeassistant.const
# ---------------------------------------------------------------------------


class EntityCategory:
    DIAGNOSTIC = "diagnostic"
    CONFIG = "config"


class UnitOfTemperature:
    CELSIUS = "°C"
    FAHRENHEIT = "°F"


class UnitOfTime:
    HOURS = "h"
    DAYS = "d"
    MINUTES = "min"


class UnitOfInformation:
    GIGABYTES = "GB"


# ---------------------------------------------------------------------------
# homeassistant.util
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    """Minimal slugify matching HA's implementation for our test assertions."""
    import re

    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    text = text.strip("_")
    return text


# ---------------------------------------------------------------------------
# homeassistant.helpers.aiohttp_client
# ---------------------------------------------------------------------------


def async_get_clientsession(hass, verify_ssl=True) -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# homeassistant.helpers.entity_platform
# ---------------------------------------------------------------------------

AddEntitiesCallback = callable


# ---------------------------------------------------------------------------
# Install stubs into sys.modules so integration imports resolve correctly
# ---------------------------------------------------------------------------


def install() -> None:
    """Call once before importing any integration module."""

    def _mod(name: str, **attrs) -> MagicMock:
        m = MagicMock()
        m.__name__ = name
        for k, v in attrs.items():
            setattr(m, k, v)
        return m

    ha_core = _mod("homeassistant.core", HomeAssistant=HomeAssistant)
    ha_exc = _mod(
        "homeassistant.exceptions",
        ConfigEntryNotReady=ConfigEntryNotReady,
    )
    ha_ce = _mod(
        "homeassistant.config_entries",
        ConfigEntry=ConfigEntry,
        ConfigFlow=ConfigFlow,
        OptionsFlow=OptionsFlow,
    )
    ha_flow = _mod("homeassistant.data_entry_flow")

    # device_registry module
    ha_dr_mod = sys.modules.get("homeassistant.helpers.device_registry") or _mod(
        "homeassistant.helpers.device_registry"
    )
    ha_dr_mod.async_get = async_get
    ha_dr_mod.async_entries_for_config_entry = async_entries_for_config_entry
    ha_dr_mod.DeviceRegistry = DeviceRegistry
    ha_dr_mod.DeviceEntry = DeviceEntry
    ha_dr_mod.DeviceEntryType = DeviceEntryType
    ha_dr_mod.DeviceInfo = DeviceInfo

    # entity_registry module
    ha_er_mod = sys.modules.get("homeassistant.helpers.entity_registry") or _mod(
        "homeassistant.helpers.entity_registry"
    )
    ha_er_mod.async_get = er_async_get
    ha_er_mod.async_entries_for_config_entry = er_async_entries_for_config_entry
    ha_er_mod.EntityRegistry = EntityRegistry
    ha_er_mod.EntityEntry = EntityEntry

    ha_entity = _mod("homeassistant.helpers.entity", DeviceInfo=DeviceInfo)
    ha_coord = _mod(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=DataUpdateCoordinator,
        CoordinatorEntity=CoordinatorEntity,
        UpdateFailed=UpdateFailed,
    )
    ha_aiohttp = _mod(
        "homeassistant.helpers.aiohttp_client",
        async_get_clientsession=async_get_clientsession,
    )
    ha_ep = _mod(
        "homeassistant.helpers.entity_platform",
        AddEntitiesCallback=AddEntitiesCallback,
    )
    ha_helpers = _mod(
        "homeassistant.helpers",
        device_registry=ha_dr_mod,
        entity_registry=ha_er_mod,
    )

    ha_sensor = _mod(
        "homeassistant.components.sensor",
        SensorEntity=SensorEntity,
        SensorStateClass=SensorStateClass,
        SensorDeviceClass=SensorDeviceClass,
        SensorEntityDescription=SensorEntityDescription,
    )

    ha_const = _mod(
        "homeassistant.const",
        EntityCategory=EntityCategory,
        UnitOfTemperature=UnitOfTemperature,
        UnitOfTime=UnitOfTime,
        UnitOfInformation=UnitOfInformation,
    )

    ha_util_mod = _mod("homeassistant.util", slugify=slugify)

    ha_top = _mod("homeassistant", config_entries=ha_ce)

    mods = {
        "homeassistant": ha_top,
        "homeassistant.core": ha_core,
        "homeassistant.exceptions": ha_exc,
        "homeassistant.config_entries": ha_ce,
        "homeassistant.data_entry_flow": ha_flow,
        "homeassistant.helpers": ha_helpers,
        "homeassistant.helpers.device_registry": ha_dr_mod,
        "homeassistant.helpers.entity_registry": ha_er_mod,
        "homeassistant.helpers.entity": ha_entity,
        "homeassistant.helpers.update_coordinator": ha_coord,
        "homeassistant.helpers.aiohttp_client": ha_aiohttp,
        "homeassistant.helpers.entity_platform": ha_ep,
        "homeassistant.components.sensor": ha_sensor,
        "homeassistant.const": ha_const,
        "homeassistant.util": ha_util_mod,
        "voluptuous": _mod(
            "voluptuous",
            Schema=MagicMock(return_value=MagicMock()),
            Required=lambda k, **kw: k,
            Optional=lambda k, **kw: k,
            All=lambda *a: a[0],
            Coerce=lambda t: t,
            Range=lambda **kw: lambda x: x,
        ),
        "aiohttp": _mod("aiohttp", ClientSession=MagicMock, ClientResponse=MagicMock),
    }
    for name, mod in mods.items():
        if name not in sys.modules:
            sys.modules[name] = mod
