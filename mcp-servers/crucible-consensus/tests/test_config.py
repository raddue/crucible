import pytest
import yaml
from pathlib import Path

from config import (
    load_config, load_external_review_config,
    ConfigError, ConsensusConfig, ModelConfig, ExternalReviewConfig,
)


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Helper to write a consensus config YAML into a tmp project dir."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    config_file = claude_dir / "consensus-config.yaml"
    config_file.write_text(yaml.dump(data))
    return tmp_path


VALID_CONSENSUS_SECTION = {
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

VALID_YAML = {"consensus": VALID_CONSENSUS_SECTION}


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

    data = {"consensus": {**VALID_CONSENSUS_SECTION, "min_models": 3}}
    project_dir = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="min_models \\(3\\) exceeds configured model count \\(2\\)"):
        load_config(str(project_dir))


def test_unsupported_provider_raises(tmp_path, monkeypatch):
    """Provider 'cohere' raises ConfigError with 'not yet supported' message."""
    monkeypatch.setenv("COHERE_API_KEY", "co-test")

    data = {
        "consensus": {
            "models": [
                {
                    "provider": "cohere",
                    "model_id": "command-r-plus",
                    "api_key_env": "COHERE_API_KEY",
                },
            ],
        },
    }
    project_dir = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="not yet supported"):
        load_config(str(project_dir))


def test_defaults_applied(tmp_path, monkeypatch):
    """YAML with only models list gets default values for optional fields."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test-456")

    data = {
        "consensus": {
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
        },
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

    data = {"consensus": {**VALID_CONSENSUS_SECTION, "enabled": False}}
    project_dir = _write_config(tmp_path, data)
    config = load_config(str(project_dir))

    assert config.enabled is False


def test_nested_consensus_key(tmp_path, monkeypatch):
    """Config nested under 'consensus:' key loads correctly (matches example YAML)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test-456")

    nested_data = {"consensus": VALID_CONSENSUS_SECTION}
    project_dir = _write_config(tmp_path, nested_data)
    config = load_config(str(project_dir))

    assert config.enabled is True
    assert config.min_models == 2
    assert config.timeout_seconds == 90
    assert len(config.models) == 2
    assert config.models[0].provider == "anthropic"
    assert config.models[0].model_id == "claude-sonnet-4-20250514"
    assert config.models[1].provider == "google"
    assert config.models[1].model_id == "gemini-2.0-flash"
    assert config.modes == {"review": True, "verdict": False, "investigate": True}


def test_flat_format_config_loads(tmp_path, monkeypatch):
    """Flat YAML (no consensus: wrapper) loads correctly for backward compat."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test-456")

    flat_data = VALID_CONSENSUS_SECTION  # No consensus: wrapper
    project_dir = _write_config(tmp_path, flat_data)
    config = load_config(str(project_dir))

    assert config.enabled is True
    assert len(config.models) == 2
    assert config.models[0].provider == "anthropic"


def test_flat_format_not_confused_by_external_review(tmp_path, monkeypatch):
    """Nested config with external_review sibling doesn't leak into consensus."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test-456")

    data = {
        "external_review": {
            "enabled": True,
            "models": [{"provider": "google", "model_id": "gemini", "api_key_env": "GOOGLE_API_KEY"}],
        }
    }
    project_dir = _write_config(tmp_path, data)

    # No consensus section + external_review sibling → min_models(2) > 0 models → ConfigError
    # This proves external_review models did NOT leak into consensus parsing
    with pytest.raises(ConfigError, match="min_models"):
        load_config(str(project_dir))


# ── External Review Config Tests ──────────────────────────────────────


EXTERNAL_REVIEW_ONE_MODEL = {
    "external_review": {
        "enabled": True,
        "timeout_seconds": 200,
        "temperature": 0.4,
        "models": [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "api_key_env": "OPENAI_API_KEY",
            },
        ],
    },
}


EXTERNAL_REVIEW_TWO_MODELS = {
    "external_review": {
        "enabled": True,
        "models": [
            {
                "provider": "openai",
                "model_id": "gpt-4o",
                "api_key_env": "OPENAI_API_KEY",
                "temperature": 0.8,
            },
            {
                "provider": "anthropic",
                "model_id": "claude-sonnet-4-20250514",
                "api_key_env": "ANTHROPIC_API_KEY",
                "base_url_env": "ANTHROPIC_BASE_URL",
            },
        ],
        "skills": {
            "inquisitor": True,
        },
    },
}


def test_external_review_one_model(tmp_path, monkeypatch):
    """Valid config with 1 external model parses correctly."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    project_dir = _write_config(tmp_path, EXTERNAL_REVIEW_ONE_MODEL)
    config = load_external_review_config(str(project_dir))

    assert config.enabled is True
    assert config.timeout_seconds == 200
    assert len(config.models) == 1
    assert config.models[0].provider == "openai"
    assert config.models[0].model_id == "gpt-4o"
    assert config.models[0].temperature == 0.4  # inherited from section
    assert config.models[0].base_url_env is None


def test_external_review_two_models(tmp_path, monkeypatch):
    """Valid config with 2 external models parses both."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://custom.api.example.com")

    project_dir = _write_config(tmp_path, EXTERNAL_REVIEW_TWO_MODELS)
    config = load_external_review_config(str(project_dir))

    assert config.enabled is True
    assert len(config.models) == 2
    assert config.models[0].provider == "openai"
    assert config.models[0].temperature == 0.8  # per-model override
    assert config.models[1].provider == "anthropic"
    assert config.models[1].base_url_env == "ANTHROPIC_BASE_URL"
    assert config.models[1].temperature == 0.3  # section default
    # Skills merged with defaults
    assert config.skills["inquisitor"] is True
    assert config.skills["code_review"] is True


def test_external_review_missing_section(tmp_path, monkeypatch):
    """Missing external_review section returns disabled config."""
    project_dir = _write_config(tmp_path, {"consensus": {"enabled": True}})
    config = load_external_review_config(str(project_dir))

    assert config.enabled is False
    assert config.models == []


def test_external_review_missing_file(tmp_path):
    """Missing config file returns disabled config (no error)."""
    config = load_external_review_config(str(tmp_path))

    assert config.enabled is False
    assert config.models == []


def test_external_review_missing_api_key(tmp_path, monkeypatch):
    """Missing API key env var raises ConfigError."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    project_dir = _write_config(tmp_path, EXTERNAL_REVIEW_ONE_MODEL)

    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_external_review_config(str(project_dir))


def test_external_review_unknown_provider(tmp_path, monkeypatch):
    """Unknown provider raises ConfigError."""
    monkeypatch.setenv("COHERE_KEY", "co-test")

    data = {
        "external_review": {
            "enabled": True,
            "models": [
                {
                    "provider": "cohere",
                    "model_id": "command-r",
                    "api_key_env": "COHERE_KEY",
                },
            ],
        },
    }
    project_dir = _write_config(tmp_path, data)

    with pytest.raises(ConfigError, match="not yet supported"):
        load_external_review_config(str(project_dir))


def test_external_review_disabled(tmp_path):
    """Disabled config (enabled: false) returns disabled config."""
    data = {
        "external_review": {
            "enabled": False,
            "models": [
                {
                    "provider": "openai",
                    "model_id": "gpt-4o",
                    "api_key_env": "OPENAI_API_KEY",
                },
            ],
        },
    }
    project_dir = _write_config(tmp_path, data)
    config = load_external_review_config(str(project_dir))

    assert config.enabled is False
    assert config.models == []


def test_external_review_skill_defaults(tmp_path, monkeypatch):
    """Skill toggle defaults when skills key is absent."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")

    project_dir = _write_config(tmp_path, EXTERNAL_REVIEW_ONE_MODEL)
    config = load_external_review_config(str(project_dir))

    assert config.skills == {
        "code_review": True,
        "quality_gate": True,
        "red_team": True,
        "inquisitor": False,
    }


def test_external_review_temperature_precedence(tmp_path, monkeypatch):
    """Per-model temperature overrides section-level temperature."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

    data = {
        "external_review": {
            "enabled": True,
            "temperature": 0.5,
            "models": [
                {
                    "provider": "openai",
                    "model_id": "gpt-4o",
                    "api_key_env": "OPENAI_API_KEY",
                    "temperature": 0.9,
                },
                {
                    "provider": "anthropic",
                    "model_id": "claude-sonnet-4-20250514",
                    "api_key_env": "ANTHROPIC_API_KEY",
                },
            ],
        },
    }
    project_dir = _write_config(tmp_path, data)
    config = load_external_review_config(str(project_dir))

    assert config.models[0].temperature == 0.9  # per-model override
    assert config.models[1].temperature == 0.5  # section-level default


# ---------------------------------------------------------------------------
# Timeout validation tests
# ---------------------------------------------------------------------------


def test_consensus_timeout_zero_raises(tmp_path, monkeypatch):
    """timeout_seconds=0 raises ConfigError."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    data = {
        "enabled": True,
        "min_models": 1,
        "timeout_seconds": 0,
        "models": [
            {"provider": "anthropic", "model_id": "claude-sonnet-4-20250514", "api_key_env": "ANTHROPIC_API_KEY"},
        ],
    }
    project_dir = _write_config(tmp_path, data)
    with pytest.raises(ConfigError, match="timeout_seconds"):
        load_config(str(project_dir))


def test_consensus_timeout_601_raises(tmp_path, monkeypatch):
    """timeout_seconds=601 raises ConfigError."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    data = {
        "enabled": True,
        "min_models": 1,
        "timeout_seconds": 601,
        "models": [
            {"provider": "anthropic", "model_id": "claude-sonnet-4-20250514", "api_key_env": "ANTHROPIC_API_KEY"},
        ],
    }
    project_dir = _write_config(tmp_path, data)
    with pytest.raises(ConfigError, match="timeout_seconds"):
        load_config(str(project_dir))


def test_consensus_timeout_boundary_valid(tmp_path, monkeypatch):
    """timeout_seconds=1 and timeout_seconds=600 are both valid."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    for timeout in (1, 600):
        data = {
            "enabled": True,
            "min_models": 1,
            "timeout_seconds": timeout,
            "models": [
                {"provider": "anthropic", "model_id": "claude-sonnet-4-20250514", "api_key_env": "ANTHROPIC_API_KEY"},
            ],
        }
        project_dir = _write_config(tmp_path, data)
        config = load_config(str(project_dir))
        assert config.timeout_seconds == timeout


def test_external_review_timeout_zero_raises(tmp_path, monkeypatch):
    """External review timeout_seconds=0 raises ConfigError."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    data = {
        "external_review": {
            "enabled": True,
            "timeout_seconds": 0,
            "models": [
                {"provider": "openai", "model_id": "gpt-4o", "api_key_env": "OPENAI_API_KEY"},
            ],
        },
    }
    project_dir = _write_config(tmp_path, data)
    with pytest.raises(ConfigError, match="timeout_seconds"):
        load_external_review_config(str(project_dir))


def test_external_review_config_no_temperature_field():
    """ExternalReviewConfig no longer has a temperature field."""
    assert "temperature" not in ExternalReviewConfig.__dataclass_fields__
