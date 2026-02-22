"""Root conftest for PI Thermostat tests.

Provides common fixtures and enables custom integration discovery
for tests that need a full Home Assistant instance.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:  # noqa: ARG001
    """Enable custom integrations for all tests that use the hass fixture.

    This fixture is auto-used so every test can discover the custom_components
    directory without explicitly requesting enable_custom_integrations.
    """
