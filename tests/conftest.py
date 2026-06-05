"""Fixtures for the becker integration tests.

This repository keeps the integration files in the repository root (HACS
content_in_root layout). The Home Assistant test harness expects them under
custom_components/becker, so copy them there before anything imports the
integration. Symlinks do not work: pytest's import hook resolves them back
to the repository root and fails to map the module name.
"""

from collections.abc import Generator
from pathlib import Path
import shutil
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_DEVICE, CONF_FILENAME
from homeassistant.core import HomeAssistant

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / "custom_components" / "becker"

COPIED = [
    "__init__.py",
    "config_flow.py",
    "const.py",
    "cover.py",
    "travelcalculator.py",
    "manifest.json",
    "services.yaml",
    "strings.json",
    "translations",
    "pybecker",
]

shutil.rmtree(PACKAGE, ignore_errors=True)
PACKAGE.mkdir(parents=True)
for name in COPIED:
    source = ROOT / name
    if source.is_dir():
        shutil.copytree(source, PACKAGE / name, ignore=shutil.ignore_patterns("__pycache__"))
    else:
        shutil.copy2(source, PACKAGE / name)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custom_components.becker.const import (  # noqa: E402
    CONF_CHANNEL,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_DB_FILENAME,
    DOMAIN,
    SUBENTRY_TYPE_COVER,
)

TEST_DEVICE = "/dev/ttyUSB0"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Enable loading custom integrations."""
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent actual entry setup in config flow tests."""
    with patch(
        "custom_components.becker.async_setup_entry", return_value=True
    ) as setup_entry:
        yield setup_entry


@pytest.fixture
def mock_test_connection() -> Generator[MagicMock]:
    """Mock the blocking connection test in the config flow."""
    with patch(
        "custom_components.becker.config_flow._test_connection"
    ) as test_connection:
        yield test_connection


@pytest.fixture
def mock_becker() -> Generator[MagicMock]:
    """Mock the pybecker Becker controller."""
    with patch("custom_components.becker.Becker", autospec=True) as becker_class:
        becker = becker_class.return_value
        becker.init_unconfigured_unit = AsyncMock()
        yield becker


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for a serial stick without covers."""
    return MockConfigEntry(
        title="Becker (ttyUSB0)",
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_DEVICE: TEST_DEVICE,
            CONF_FILENAME: DEFAULT_DB_FILENAME,
        },
        unique_id=TEST_DEVICE,
    )


@pytest.fixture
def mock_config_entry_with_cover() -> MockConfigEntry:
    """Return a config entry with one cover subentry."""
    return MockConfigEntry(
        title="Becker (ttyUSB0)",
        domain=DOMAIN,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_DEVICE: TEST_DEVICE,
            CONF_FILENAME: DEFAULT_DB_FILENAME,
        },
        unique_id=TEST_DEVICE,
        subentries_data=[
            {
                "subentry_type": SUBENTRY_TYPE_COVER,
                "title": "Kitchen",
                "unique_id": "1",
                "data": {
                    CONF_CHANNEL: "1",
                    "friendly_name": "Kitchen",
                },
            }
        ],
    )
