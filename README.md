[![hacs_badge](https://img.shields.io/badge/HACS-Default-teal.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/vitals5/ha_scrutiny?style=plastic)](https://github.com/vitals5/ha_scrutiny/releases)

![Scrutiny Banner](brands/ha_scrutiny_banner.png)

# Scrutiny — Home Assistant Integration

Monitor the health of your hard drives directly in Home Assistant by connecting to a running [Scrutiny](https://github.com/AnalogJ/scrutiny) instance. Scrutiny collects S.M.A.R.T. data from your drives using `smartctl` and applies real-world failure-rate thresholds from BackBlaze research to give you more meaningful pass/fail indicators than raw SMART values alone.

---

## What it does

For every disk monitored by your Scrutiny server, this integration creates a Home Assistant **device** and exposes the following **sensor entities**:

| Sensor | Description | Unit |
|---|---|---|
| **Overall Status** | Scrutiny's combined health assessment | Enum |
| **SMART Test Result** | Result of the latest SMART self-test snapshot | Enum |
| **Temperature** | Current drive temperature | °C |
| **Power On Time** | Total accumulated powered-on time | h (displayed as days) |
| **Power Cycle Count** | Number of times the drive has been power-cycled | — |
| **Capacity** | Drive capacity | GB |

In addition, sensor entities for individual SMART attributes can be enabled through the integration options. These match Scrutiny's own drill-down hierarchy — critical attributes first, then all attributes on demand.

### Device identity

Devices are named after their **model and serial number** (e.g. `WD Red Plus 4TB (WD40EFZX-12345)`) so you can cross-reference them against TrueNAS, ZFS, or any other tool that identifies disks by serial number. The underlying unique identifier used by Home Assistant is the **Scrutiny disk ID** — a UUIDv5 on Scrutiny ≥ 0.9.0, or the WWN hex string on older releases. Either way it remains stable across reboots and drive path changes. Each disk device includes a **Visit** link that opens its page directly in the Scrutiny UI.

### Device path (current `/dev/sdX`)

The current device path (e.g. `/dev/sda`) is exposed as the `device_name` attribute on every sensor entity for that disk. You can see it in the entity's attribute panel in the Home Assistant UI. Because Linux device paths are not guaranteed to be stable across reboots, the path shown may not always reflect the current system state — it reflects whatever path Scrutiny last reported. The drive's stable identity in Home Assistant is always the Scrutiny disk ID.

---

## Requirements

- Home Assistant 2026.3 or newer
- A reachable [Scrutiny](https://github.com/AnalogJ/scrutiny) instance (self-hosted, Docker, or TrueNAS App)
- Network access from Home Assistant to the Scrutiny web interface

---

## Installation

### HACS (Recommended)

This integration is available in the default HACS catalog.

1. Open HACS in Home Assistant
2. Go to **Integrations**
3. Search for **Scrutiny** and install it
4. Restart Home Assistant

Or click the button below to install directly:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vitals5&repository=ha_scrutiny&category=integration)

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/scrutiny` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings → Devices & Services → Add Integration**.
2. Search for **Scrutiny** and select it.
3. Enter the connection and option details:

| Field | Description | Default |
|---|---|---|
| **URL** | Full URL of your Scrutiny server, e.g. `http://scrutiny.local:8080` or `https://scrutiny.example.com` | — |
| **Verify SSL certificate** | Uncheck only if using a self-signed certificate | On |
| **Scan Interval** | How often to poll Scrutiny for new data (minutes) | `60` |
| **Show archived disks** | Include disks archived in Scrutiny | Off |
| **Critical SMART attribute sensors** | Create sensors for Scrutiny-flagged critical attributes | Off |
| **All SMART attribute sensors** | Create sensors for every reported SMART attribute | Off |
| **Enable raw value sensors** | Create numeric sensors for raw SMART attribute values (enables history and long-term statistics) | Off |

Home Assistant will test the connection before saving. If Scrutiny is not reachable the setup will fail with a clear error message.

### Changing settings later

Two separate screens handle post-setup changes — this is intentional HA design:

**Configure** (gear icon): Optional tuning that doesn't affect connectivity. Includes scan interval, archived disk visibility, and entity level options.

**Reconfigure** (three-dot menu → Reconfigure): Change the URL or SSL verification setting. Requires a connection test and integration reload.

### About SMART attribute sensor tiers

The sensor tiers mirror the Scrutiny web UI's own drill-down structure:

1. **Default** (always created): Overall Status, SMART Test Result, Temperature, Power On Time, Power Cycle Count, Capacity — the six metrics shown on the Scrutiny dashboard.
2. **Critical** (opt-in): Attributes that Scrutiny's research flags as predictive of failure — shown when you click into a drive in the Scrutiny UI.
3. **All** (opt-in): Every attribute the drive reports, including informational ones. Can add dozens of sensors per drive. Enabling this overrides the critical-only setting.

**Enable raw value sensors** pairs with whichever attribute tier is active. For each attribute sensor created, a companion numeric sensor is also created for the raw integer value. This gives Home Assistant a state value it can record in its history database and plot over time — making slow degradation trends visible (e.g. a gradually climbing Reallocated Sectors Count). Raw value sensors are only created for attributes already enabled by the tier selection above.

### About archived disks

Scrutiny lets you archive drives that are no longer physically present to preserve their SMART history. By default this integration hides archived drives and removes their HA devices automatically. Enable **Show archived disks** to keep them visible — they appear with an `[Archived]` suffix on the device name and an `archived: true` extra attribute on all their sensors.

---

## Supported platforms

This integration has been tested against Scrutiny running in the following configurations:

- **Docker** (omnibus image — single container with web + collector)
- **Docker** (hub/spoke — separate web, influxdb, and collector containers)
- **TrueNAS SCALE** (via the Scrutiny community app)

Any deployment that exposes the standard Scrutiny HTTP API on a reachable address should work.

### Known limitations

- Scrutiny only updates SMART data when its collector runs (typically once per day by default). Polling Home Assistant more frequently than the collector runs will not produce newer data — the limiting factor is always the collector schedule, not the integration's scan interval.
- Drives that appear in Scrutiny but have no SMART data yet (e.g. newly registered drives that haven't had a collector run) will show sensors in an unavailable state until data is collected.
- This integration does not trigger Scrutiny's collector — it only reads data. Schedule the collector separately (cron, Docker restart policy, etc.).

---

## Automations & use cases

### Alert when a drive fails

Replace `sensor.your_drive_overall_status` with the entity ID for your drive's Overall Status sensor, found in **Settings → Devices & Services → Scrutiny → your drive → entities**.

```yaml
automation:
  - alias: "Notify on drive failure"
    trigger:
      - platform: state
        entity_id: sensor.your_drive_overall_status
        to: "Failed (S.M.A.R.T.)"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Drive Health Alert"
          message: >
            {{ trigger.to_state.attributes.friendly_name }} has failed.
            Check Scrutiny for details.
```

### Alert when temperature is high

```yaml
automation:
  - alias: "Notify on high drive temperature"
    trigger:
      - platform: numeric_state
        entity_id: sensor.your_drive_temperature
        above: 55
    action:
      - service: notify.persistent_notification
        data:
          title: "High Drive Temperature"
          message: "{{ trigger.entity_id }} is {{ trigger.to_state.state }}°C"
```

### Dashboard card

A simple Entities card for a single drive (replace entity IDs with your own from the device page):

```yaml
type: entities
title: "Drive Health"
entities:
  - sensor.your_drive_overall_status
  - sensor.your_drive_smart_test_result
  - sensor.your_drive_temperature
  - sensor.your_drive_power_on_time
  - sensor.your_drive_capacity
```

---

## Data update and polling

Home Assistant polls the Scrutiny API on the configured scan interval. On each poll:

1. The `/api/summary` endpoint is called to get current status and basic metrics for all disks.
2. The `/api/device/{disk_id}/details` endpoint is called **concurrently** for every disk to retrieve the latest SMART snapshot and attribute metadata.

If the Scrutiny server is temporarily unreachable, sensors are marked unavailable and Home Assistant logs a single warning. Polling resumes automatically at the next interval — no restart is required.

Keep in mind that the **Scrutiny collector schedule** is the true data refresh rate. Polling Home Assistant more frequently than the collector runs will not produce newer SMART readings. If your collector runs daily (the default), there is little benefit to setting the scan interval shorter than a few hours.

---

## Troubleshooting

### "Cannot connect" during setup

- Confirm Scrutiny is running and the web UI is accessible in a browser at `http://<host>:<port>`.
- Check that Home Assistant can reach the host over the network (no firewall blocking the port).
- If using a reverse proxy in front of Scrutiny, ensure the proxy correctly forwards requests to the API path `/api/`.

### Sensors show "Unavailable"

- Scrutiny's collector may not have run yet — check the Scrutiny web UI to confirm drives appear there with data.
- The Scrutiny server may have restarted or become temporarily unreachable. HA will recover automatically at the next poll.
- If a specific SMART attribute sensor is unavailable, that attribute may not have been reported in the latest collector run for that drive.

### Entities not updating

- Check the Home Assistant logs (`Settings → System → Logs`) for errors from the `custom_components.scrutiny` logger.
- Remember that the collector schedule — not the integration's scan interval — determines when new SMART data is available. If the collector runs daily, sensor values will only change once per day regardless of how frequently HA polls.

### Downloading diagnostic information

If you need to file a bug report, diagnostic data can be downloaded from:

**Settings → Devices & Services → Scrutiny → (three-dot menu) → Download Diagnostics**

---

## Removal

To remove the integration:

1. Go to **Settings → Devices & Services**.
2. Find the Scrutiny integration card.
3. Click the three-dot menu → **Delete**.
4. Restart Home Assistant.

All devices and entities created by the integration will be removed automatically.

---

## Attribution

Originally created by **[@vitals5](https://github.com/vitals5)**. Substantially developed and maintained by **[@raetha](https://github.com/raetha)**, with design assistance and code generation by **[Claude](https://claude.ai)** (Anthropic).

For the Scrutiny application itself (collector, web server, API), see [AnalogJ/scrutiny](https://github.com/AnalogJ/scrutiny).

---

## Contributing

Issues and pull requests are welcome at [vitals5/ha_scrutiny](https://github.com/vitals5/ha_scrutiny).

---

## License

MIT — see [LICENSE](LICENSE).
