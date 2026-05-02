# Changelog

## [1.1.1] — 2026-04-30

### Repository

- Transferred to [vitals5/ha_scrutiny](https://github.com/vitals5/ha_scrutiny) as the
  primary upstream repository.
- `manifest.json` — `codeowners` updated to `["@vitals5", "@raetha"]`; `documentation`
  and `issue_tracker` URLs updated to the upstream repository.
- `LICENSE` — added `Copyright (c) 2024 vitals5` to correctly reflect the original
  author alongside the fork author.
- `README.md` — HACS badge updated from "Custom" to "Default" (the integration is in
  the default HACS catalog); install instructions simplified accordingly; banner image
  restored; attribution and all repository URLs updated to upstream.
- `CONTRIBUTING.md` — repository URL updated to upstream.
- `CHANGELOG.md` — compare links updated to upstream repository.
- `.github/FUNDING.yml` — removed (personal funding link, not appropriate in a shared
  upstream repository).

## [1.1.0] — 2026-04-30

### Scrutiny 0.9.0 compatibility

Scrutiny 0.9.0 replaced WWN hex strings with UUIDv5 values as the primary disk
identifier in its API routes and summary response. The integration was already
functionally compatible — it treats summary dict keys as opaque strings — but all
internal variable names and comments still said "WWN" when they meant "the disk
identifier Scrutiny returned". This release corrects that:

- **Renamed `wwn` → `disk_id` throughout** — loop variables, constructor parameters,
  instance attributes, and log messages. `ATTR_WWN` is unchanged; it is the `"wwn"`
  JSON field within the device payload, which is still present in 0.9.x.
- **`diagnostics.py`** — fixed a bug where the `"wwn"` diagnostics field was being
  read from the loop variable (the summary key) rather than the device payload. A new
  `"scrutiny_disk_id"` field now shows the opaque identifier used as the HA device key.

**Migration note:** upgrading Scrutiny from 0.8.x to 0.9.x will cause disk devices in
HA to be recreated under new UUID-based identifiers. The existing stale device cleanup
removes the old WWN-keyed devices automatically after the first successful poll.
Historical entity data will be reset, but no manual cleanup is required.

### Python and HA version

- **Python 3.14 minimum** — targets Python ≥ 3.14.2 / Home Assistant 2026.3.0.
- **Removed `from __future__ import annotations`** from all integration source files —
  lazy annotation evaluation is the default in 3.14.
- **`hacs.json`** minimum HA version updated from `2025.12.0` to `2026.3.0`.
- **`manifest.json`** — removed invalid `homeassistant` key (hassfest rejects it for
  custom integrations; minimum version belongs in `hacs.json` only).

### Bug fixes

- **Unparenthesized `except` tuples** — three instances of `except TypeError, ValueError:`
  (invalid Python 3 syntax) in `sensor.py` and `options_flow.py` corrected to
  `except (TypeError, ValueError):`.
- **`TYPE_CHECKING` imports causing runtime errors** — stdlib types (`timedelta`,
  `Logger`) and HA types used in function signatures were behind `TYPE_CHECKING` guards,
  which caused `NameError` at class-definition time once `from __future__ import
  annotations` was removed. Moved to direct runtime imports throughout.

### Test infrastructure

- **Migrated from `pytest-homeassistant-custom-component` to `ha_stubs` + stdlib
  `unittest`** — no HA installation required; suite runs in ~0.1 s with no external
  dependencies. Test count: 51 → 93.
- **`requirements.txt` renamed to `requirements_test.txt`**.
- **`pytest.ini` and `tests/conftest.py` removed** — no longer needed.
- **`tests/run_tests.py`** — combined lint + test runner; skips lint phase when
  `CI=true` (lint runs as a dedicated CI job in that environment).

### Linting and formatting

- **`ruff format` applied** to all integration source files.
- **`ruff format --check`** added to CI lint job and local runner.
- **`.ruff.toml`** — target-version `py312` → `py314`; `[format] exclude = ["tests/*"]`
  added (ruff format can silently corrupt function-local imports in test files);
  test per-file-ignores expanded to cover `E401`, `E402`, `E501`, `E702`, `F401`,
  `I001`.

### Repository structure

- **`.gitattributes`** — `* text=auto eol=lf`.
- **`.github/dependabot.yml`** — weekly updates for `github-actions` and `pip`.
- **`.github/ISSUE_TEMPLATE/`** — `bug.yml`, `feature_request.yml`, `config.yml`.
- **`CONTRIBUTING.md`** — development setup, test/lint instructions, pre-PR checklist.
- **`scripts/run_tests.sh`** — venv-managing test runner; installs ruff automatically.
- **CI** — matrix testing removed (Python 3.14 only); `ruff format --check` added to
  lint job.

## [1.0.1] — 2026-04-18

### Bug fixes

- **Raw value sensor names** — all raw value sensors displayed "Raw Value" instead of
  the attribute name (e.g. "Reallocated Sectors Count (Raw)"). Caused by `translation_key`
  overriding the programmatically set name. Fixed by removing the translation key and
  setting the icon directly via `_attr_icon`.

### CI fixes

- **`ModuleNotFoundError` in CI** — added `pythonpath = .` to `pytest.ini` so pytest
  adds the repo root to `sys.path` in clean CI environments. Also added
  `asyncio_default_fixture_loop_scope = function` to silence a pytest-asyncio
  deprecation warning.
- **Test teardown error** — `test_config_flow_user_step_success` triggered a real
  `async_setup_entry` which crashed on network access and left a background thread
  running into teardown. Fixed by mocking `async_setup_entry` in the affected tests.
- **GitHub Actions deprecation warnings** — updated `actions/checkout` v4 → v6 and
  `actions/setup-python` v5 → v6 (both now run on Node.js 24).

## [1.0.0] — 2026-04-15

Initial public release. Originally developed as a fork of [vitals5/ha_scrutiny](https://github.com/vitals5/ha_scrutiny), this is now the primary upstream repository.

This release is a substantial rewrite addressing every open issue and pending PR on the
upstream repository at the time of the fork, plus a full Home Assistant quality scale
compliance pass.

### New features

- **HTTPS / full URL configuration** — configure using a full URL instead of separate
  host and port fields, with a Verify SSL toggle for self-signed certificates.
  *(Addresses [vitals5#38](https://github.com/vitals5/ha_scrutiny/issues/38))*
- **Last SMART Update sensor** — `TIMESTAMP` entity per disk showing when Scrutiny last
  received SMART data; automation-ready (e.g. alert if no update in 48 hours).
  *(Addresses [vitals5#9](https://github.com/vitals5/ha_scrutiny/issues/9),
  [vitals5#14](https://github.com/vitals5/ha_scrutiny/pull/14))*
- **Serial number in device name** — disk devices named `Model (SerialNumber)` for easy
  cross-reference with TrueNAS, ZFS, and smartctl.
  *(Addresses [vitals5#41](https://github.com/vitals5/ha_scrutiny/issues/41))*
- **Deep-link Visit button** — Visit on a disk device opens its page directly in the
  Scrutiny UI; hub device Visit link opens the UI root.
- **SMART attribute sensors** — opt-in status sensors (Passed / Warning / Failed) per
  SMART attribute, with optional companion raw-value numeric sensors that record full
  history for trend analysis.
  *(Addresses [vitals5#39](https://github.com/vitals5/ha_scrutiny/issues/39))*
- **Archived disk support** — hidden by default; a toggle re-surfaces them.
- **Stale device cleanup** — devices for disks no longer in Scrutiny are removed
  automatically after each successful poll.
- **Configurable poll interval and entity tiers** — adjustable via the Configure screen.
- **Reconfigure flow** — URL and SSL settings updatable without losing history.

### Reliability

- **Concurrency-limited detail fetching** — up to 5 simultaneous detail requests via
  `asyncio.Semaphore`; prevents overload on large installations.
  *(Addresses [vitals5#33](https://github.com/vitals5/ha_scrutiny/pull/33))*
- **Per-disk failure isolation** — one disk failing details does not affect others.
- **Graceful error handling** — connection, API, and unexpected errors surfaced cleanly
  as `UpdateFailed`.

### Home Assistant quality scale

All Bronze, Silver, Gold, and Platinum rules satisfied. `quality_scale` set to `gold`
in `manifest.json` (the maximum accepted value; Platinum is assessed separately by the
HA core team).

---

[1.1.1]: https://github.com/vitals5/ha_scrutiny/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/vitals5/ha_scrutiny/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/vitals5/ha_scrutiny/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/vitals5/ha_scrutiny/releases/tag/v1.0.0
