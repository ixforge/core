"""Shared fixtures for UI tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _bypass_setup_middleware():
    """Skip setup redirect middleware in UI tests by mocking get_public."""
    mock = AsyncMock(return_value={"configured": True})
    with patch("ixforge.ui.api_client.APIClient.get_public", mock):
        yield
