import sys
from dataclasses import dataclass
from types import ModuleType
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
# Mock the mcp SDK so server.py imports succeed without the real package
# ---------------------------------------------------------------------------


@dataclass
class _MockTextContent:
    type: str
    text: str


@dataclass
class _MockTool:
    name: str
    description: str
    inputSchema: dict


class _MockServer:
    """Minimal mock of mcp.server.Server that makes decorators pass-through."""

    def __init__(self, name: str):
        self.name = name

    def list_tools(self):
        """Decorator that registers a list_tools handler — returns fn unchanged."""
        def decorator(fn):
            return fn
        return decorator

    def call_tool(self):
        """Decorator that registers a call_tool handler — returns fn unchanged."""
        def decorator(fn):
            return fn
        return decorator


# Build the mcp module hierarchy
_mcp_mod = ModuleType("mcp")
_mcp_server_mod = ModuleType("mcp.server")
_mcp_server_stdio_mod = ModuleType("mcp.server.stdio")
_mcp_types_mod = ModuleType("mcp.types")

_mcp_server_mod.Server = _MockServer
_mcp_server_stdio_mod.stdio_server = MagicMock()
_mcp_types_mod.Tool = _MockTool
_mcp_types_mod.TextContent = _MockTextContent

sys.modules.setdefault("mcp", _mcp_mod)
sys.modules.setdefault("mcp.server", _mcp_server_mod)
sys.modules.setdefault("mcp.server.stdio", _mcp_server_stdio_mod)
sys.modules.setdefault("mcp.types", _mcp_types_mod)


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
