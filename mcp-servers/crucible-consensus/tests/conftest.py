import sys
from unittest.mock import MagicMock

import pytest
from config import ModelConfig


# ---------------------------------------------------------------------------
# Inject mock SDK modules so provider imports succeed without real packages
# ---------------------------------------------------------------------------

# Mock the anthropic module
_mock_anthropic = MagicMock()
sys.modules.setdefault("anthropic", _mock_anthropic)

# Mock the google.genai module chain
_mock_google = MagicMock()
_mock_genai = MagicMock()
_mock_google.genai = _mock_genai
sys.modules.setdefault("google", _mock_google)
sys.modules.setdefault("google.genai", _mock_genai)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def anthropic_config(monkeypatch):
    monkeypatch.setenv("TEST_ANTHROPIC_KEY", "test-key-123")
    return ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        api_key_env="TEST_ANTHROPIC_KEY",
        temperature=0.6,
    )


@pytest.fixture
def google_config(monkeypatch):
    monkeypatch.setenv("TEST_GOOGLE_KEY", "test-key-456")
    return ModelConfig(
        provider="google",
        model_id="gemini-2.5-pro",
        api_key_env="TEST_GOOGLE_KEY",
        temperature=0.6,
    )
