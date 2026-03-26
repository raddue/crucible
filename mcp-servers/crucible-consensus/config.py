from dataclasses import dataclass, field
from pathlib import Path
import os
import yaml


SUPPORTED_PROVIDERS = {"anthropic", "google"}


class ConfigError(Exception):
    """Raised when consensus configuration is invalid."""
    pass


@dataclass
class ModelConfig:
    provider: str           # "anthropic" or "google"
    model_id: str           # e.g., "claude-sonnet-4-20250514"
    api_key_env: str        # env var name, e.g., "ANTHROPIC_API_KEY"
    temperature: float = 0.6


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

    # Parse models
    models = []
    for m in raw.get("models", []):
        models.append(ModelConfig(
            provider=m["provider"],
            model_id=m["model_id"],
            api_key_env=m["api_key_env"],
            temperature=m.get("temperature", 0.6),
        ))

    # Validate providers
    for model in models:
        if model.provider not in SUPPORTED_PROVIDERS:
            raise ConfigError(
                f"Provider '{model.provider}' is not yet supported. "
                f"Supported: anthropic, google."
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
        enabled=raw.get("enabled", True),
        min_models=raw.get("min_models", 2),
        timeout_seconds=raw.get("timeout_seconds", 120),
        models=models,
        modes=raw.get("modes", {
            "review": True,
            "verdict": True,
            "investigate": True,
        }),
    )

    # Validate min_models
    if config.min_models > len(config.models):
        raise ConfigError(
            f"min_models ({config.min_models}) exceeds configured model count "
            f"({len(config.models)})"
        )

    return config
