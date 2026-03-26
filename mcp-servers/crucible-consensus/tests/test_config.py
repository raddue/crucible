import pytest
import yaml
from pathlib import Path

from config import load_config, ConfigError, ConsensusConfig, ModelConfig


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Helper to write a consensus config YAML into a tmp project dir."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    config_file = claude_dir / "consensus-config.yaml"
    config_file.write_text(yaml.dump(data))
    return tmp_path


VALID_YAML = {
    "enabled": True,
    "min_models": 2,
    "timeout_seconds": 90,
    "models": [
        {
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-20250514",
            "api_key_env": "ANTHROPIC_API_KEY",
            "temperature": 0.7,
        },
        {
            "provider": "google",
            "model_id": "gemini-2.0-flash",
            "api_key_env": "GOOGLE_API_KEY",
            "temperature": 0.5,
        },
    ],
    "modes": {
        "review": True,
        "verdict": False,
        "investigate": True,
    },
}


def test_valid_config_loads(tmp_path, monkeypatch):
    """Valid YAML with env vars set loads all fields correctly."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test-456")

    project_dir = _write_config(tmp_path, VALID_YAML)
    config = load_config(str(project_dir))

    assert config.enabled is True
    assert config.min_models == 2
    assert config.timeout_seconds == 90
    assert len(config.models) == 2

    assert config.models[0].provider == "anthropic"
    assert config.models[0].model_id == "claude-sonnet-4-20250514"
    assert config.models[0].api_key_env == "ANTHROPIC_API_KEY"
    assert config.models[0].temperature == 0.7

    assert config.models[1].provider == "google"
    assert config.models[1].model_id == "gemini-2.0-flash"
    assert config.models[1].api_key_env == "GOOGLE_API_KEY"
    assert config.models[1].temperature == 0.5

    assert config.modes == {"review": True, "verdict": False, "investigate": True}


def test_missing_config_file_raises(tmp_path):
    """No YAML file raises ConfigError with the expected path."""
    with pytest.raises(ConfigError, match="Consensus config not found"):
        load_config(str(tmp_path))


def test_missing_env_var_raises(tmp_path, monkeypatch):
    """Valid YAML but missing env var raises ConfigError naming the variable."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    project_dir = _write_config(tmp_path, VALID_YAML)

    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        load_config(str(project_dir))


def test_min_models_exceeds_count_raises(tmp_path, monkeypatch):
    """min_models=3 with only 2 models raises ConfigError."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test-456")

    data = {**VALID_YAML, "min_models": 3}
    project_dir = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="min_models \\(3\\) exceeds configured model count \\(2\\)"):
        load_config(str(project_dir))


def test_unsupported_provider_raises(tmp_path, monkeypatch):
    """Provider 'openai' raises ConfigError with 'not yet supported' message."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    data = {
        "models": [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "api_key_env": "OPENAI_API_KEY",
            },
        ],
    }
    project_dir = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="not yet supported"):
        load_config(str(project_dir))


def test_defaults_applied(tmp_path, monkeypatch):
    """YAML with only models list gets default values for optional fields."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test-456")

    data = {
        "models": [
            {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-20250514",
                "api_key_env": "ANTHROPIC_API_KEY",
            },
            {
                "provider": "google",
                "model_id": "gemini-2.0-flash",
                "api_key_env": "GOOGLE_API_KEY",
            },
        ],
    }
    project_dir = _write_config(tmp_path, data)
    config = load_config(str(project_dir))

    assert config.enabled is True
    assert config.min_models == 2
    assert config.timeout_seconds == 120
    assert config.modes == {"review": True, "verdict": True, "investigate": True}
    # Default temperature on models
    assert config.models[0].temperature == 0.6
    assert config.models[1].temperature == 0.6


def test_enabled_false(tmp_path, monkeypatch):
    """Config with enabled: false loads successfully."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test-456")

    data = {**VALID_YAML, "enabled": False}
    project_dir = _write_config(tmp_path, data)
    config = load_config(str(project_dir))

    assert config.enabled is False
