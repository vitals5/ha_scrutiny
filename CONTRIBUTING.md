# Contributing

Contributions are welcome via pull requests at [vitals5/ha_scrutiny](https://github.com/vitals5/ha_scrutiny).

## Development setup

1. Clone the repository
2. Install test dependencies: `pip install ruff` (requires Python 3.14+)
3. Run the full suite (lint + tests): `python3 tests/run_tests.py`
4. Or use the venv script: `bash scripts/run_tests.sh`

## Before submitting a PR

- All tests pass (`python3 tests/run_tests.py`)
- Ruff reports no lint issues (`ruff check custom_components/scrutiny/`)
- Ruff formatting is clean (`ruff format --check custom_components/scrutiny/`)
- If adding a new feature, update `CHANGELOG.md` under the current unreleased section
- `custom_components/scrutiny/manifest.json` version is **not** bumped (maintainer handles releases)

## Testing approach

The test suite uses Python's stdlib `unittest` with a lightweight `ha_stubs` module
that provides accurate minimal stubs for all HA classes used by the integration.
No Home Assistant installation or external test framework is required — tests run
in plain Python with no network access needed.

## Project structure

```
custom_components/scrutiny/   Integration source (api, coordinator, sensor, flows, const, …)
tests/
  ha_stubs.py                 Lightweight stubs for HA classes — no HA install needed
  run_tests.py                Test runner entry point (lint + tests)
  test_api.py                 API client tests
  test_coordinator.py         Coordinator + data processing tests
  test_config_flow.py         Config flow tests
  test_options_flow.py        Options flow tests
  test_sensor.py              Sensor platform tests
scripts/
  run_tests.sh                Shell wrapper that manages a .venv and installs ruff
  bump_version.sh             Version bump helper (maintainer use only)
```
