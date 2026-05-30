from dataclasses import dataclass, field
from pathlib import Path
import os
import yaml


SUPPORTED_PROVIDERS = {"anthropic", "google", "openai"}


class ConfigError(Exception):
    """Raised when consensus configuration is invalid."""
    pass


@dataclass
class ModelConfig:
    provider: str           # "anthropic" or "google"
    model_id: str           # e.g., "claude-sonnet-4-20250514"
    api_key_env: str        # env var name, e.g., "ANTHROPIC_API_KEY"
    temperature: float = 0.6
    base_url_env: str | None = None


@dataclass
class ExternalReviewConfig:
    enabled: bool = False
    models: list[ModelConfig] = field(default_factory=list)
    timeout_seconds: int = 180
    skills: dict[str, bool] = field(default_factory=lambda: {
        "code_review": True,
        "quality_gate": True,
        "red_team": True,
        "inquisitor": False,
    })


@dataclass
class ConsensusConfig:
    enabled: bool = True
    min_models: int = 2
    timeout_seconds: int = 120
    models: list[ModelConfig] = field(default_factory=list)
    modes: dict[str, bool] = field(default_factory=lambda: {
        "review": True,
        "verdict": True,
        "investigate": True,
    })


def load_config(project_dir: str) -> ConsensusConfig:
    """Load and validate consensus configuration."""
    config_path = Path(project_dir) / ".claude" / "consensus-config.yaml"

    if not config_path.exists():
        raise ConfigError(f"Consensus config not found: {config_path}")

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    # Support both nested (consensus: ...) and flat formats.
    # If external_review is a sibling key, the config is nested — consensus: is required.
    # If no sibling keys, fall back to raw (flat format backward compat).
    if "consensus" in raw:
        consensus_section = raw["consensus"]
    elif "external_review" in raw:
        consensus_section = {}  # Nested format without consensus section
    else:
        consensus_section = raw  # Flat format (legacy)

    # Parse models
    models = []
    for m in consensus_section.get("models", []):
        models.append(ModelConfig(
            provider=m["provider"],
            model_id=m["model_id"],
            api_key_env=m["api_key_env"],
            temperature=m.get("temperature", 0.6),
            base_url_env=m.get("base_url_env", None),
        ))

    # Validate providers
    for model in models:
        if model.provider not in SUPPORTED_PROVIDERS:
            raise ConfigError(
                f"Provider '{model.provider}' is not yet supported. "
                f"Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
            )

    # Validate env vars
    for model in models:
        val = os.environ.get(model.api_key_env)
        if not val:
            raise ConfigError(
                f"Environment variable '{model.api_key_env}' is not set "
                f"(required by {model.provider} model)"
            )

    # Build config with defaults
    config = ConsensusConfig(
        enabled=consensus_section.get("enabled", True),
        min_models=consensus_section.get("min_models", 2),
        timeout_seconds=consensus_section.get("timeout_seconds", 120),
        models=models,
        modes=consensus_section.get("modes", {
            "review": True,
            "verdict": True,
            "investigate": True,
        }),
    )

    # Validate timeout_seconds
    if not (1 <= config.timeout_seconds <= 600):
        raise ConfigError(
            f"timeout_seconds ({config.timeout_seconds}) must be between 1 and 600"
        )

    # Validate min_models
    if config.min_models < 1:
        raise ConfigError(
            f"min_models ({config.min_models}) must be at least 1"
        )
    if config.min_models > len(config.models):
        raise ConfigError(
            f"min_models ({config.min_models}) exceeds configured model count "
            f"({len(config.models)})"
        )

    return config


def load_external_review_config(project_dir: str) -> ExternalReviewConfig:
    """Load external review configuration, returning disabled config if absent."""
    config_path = Path(project_dir) / ".claude" / "consensus-config.yaml"

    if not config_path.exists():
        return ExternalReviewConfig()

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    section = raw.get("external_review", {})
    if not section:
        return ExternalReviewConfig()

    enabled = section.get("enabled", False)
    if not enabled:
        return ExternalReviewConfig()

    section_temperature = section.get("temperature", 0.3)
    timeout_seconds = section.get("timeout_seconds", 180)

    # Parse models
    models = []
    for m in section.get("models", []):
        models.append(ModelConfig(
            provider=m["provider"],
            model_id=m["model_id"],
            api_key_env=m["api_key_env"],
            temperature=m.get("temperature", section_temperature),
            base_url_env=m.get("base_url_env", None),
        ))

    # Validate providers
    for model in models:
        if model.provider not in SUPPORTED_PROVIDERS:
            raise ConfigError(
                f"Provider '{model.provider}' is not yet supported. "
                f"Supported: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
            )

    # Validate env vars
    for model in models:
        val = os.environ.get(model.api_key_env)
        if not val:
            raise ConfigError(
                f"Environment variable '{model.api_key_env}' is not set "
                f"(required by {model.provider} model)"
            )
        # base_url_env is optional — if declared but env var is missing/empty,
        # the provider falls back to its default endpoint (no error)

    # Parse skills with defaults
    default_skills = {
        "code_review": True,
        "quality_gate": True,
        "red_team": True,
        "inquisitor": False,
    }
    skills = {**default_skills, **section.get("skills", {})}

    # Validate timeout_seconds
    if not (1 <= timeout_seconds <= 600):
        raise ConfigError(
            f"timeout_seconds ({timeout_seconds}) must be between 1 and 600"
        )

    return ExternalReviewConfig(
        enabled=True,
        models=models,
        timeout_seconds=timeout_seconds,
        skills=skills,
    )
