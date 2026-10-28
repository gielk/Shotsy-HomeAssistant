"""Fixtures for GLP-1 Tracker tests."""

from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_csv() -> str:
    return (FIXTURES / "shotsy_sample.csv").read_text()
