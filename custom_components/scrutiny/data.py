"""Custom types for scrutiny."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import ScrutinyApiClient
    from .coordinator import ScrutinyDataUpdateCoordinator


type ScrutinyConfigEntry = ConfigEntry[ScrutinyData]


@dataclass
class ScrutinyData:
    """Data for the Scrutiny integration."""

    client: ScrutinyApiClient
    coordinator: ScrutinyDataUpdateCoordinator
    integration: Integration
