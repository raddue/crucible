"""Aggregation logic for multi-model consensus."""

import json
import re
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path

from config import ConsensusConfig, ModelConfig
from providers import BaseProvider, ModelResponse, create_provider


class AggregationError(Exception):
    """Raised when aggregation fails."""
    pass


@dataclass
class ConsensusResult:
    """Structured result from consensus aggregation."""
    status: str  # "complete" | "partial" | "unavailable"
    models_queried: int = 0
    models_responded: int = 0
    synthesis: str = ""
    agreements: list[dict] = field(default_factory=list)
    disagreements: list[dict] = field(default_factory=list)
    unique_findings: list[dict] = field(default_factory=list)
    per_model: list[dict] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        """Serialize to dict for MCP tool response."""
        result = {
            "status": self.status,
            "models_queried": self.models_queried,
            "models_responded": self.models_responded,
            "synthesis": self.synthesis,
            "agreements": self.agreements,
            "disagreements": self.disagreements,
            "unique_findings": self.unique_findings,
            "per_model": self.per_model,
        }
        if self.error is not None:
            result["error"] = self.error
        return result


def load_aggregation_prompt(mode: str, prompts_dir: str) -> str:
    """Load the aggregation prompt template for the given mode.

    Args:
        mode: The consensus mode (e.g. "review", "verdict", "investigate").
        prompts_dir: Directory containing the prompt template files.

    Returns:
        The prompt template contents as a string.

    Raises:
        AggregationError: If the prompt file does not exist.
    """
    prompt_path = Path(prompts_dir) / f"aggregation-{mode}-prompt.md"
    if not prompt_path.exists():
        raise AggregationError(
            f"Aggregation prompt not found: {prompt_path}"
        )
    return prompt_path.read_text(encoding="utf-8")


def build_aggregation_input(
    responses: list[ModelResponse],
    original_prompt: str,
    original_context: str,
) -> str:
    """Format successful model responses as XML for the aggregator.

    Only includes responses where ``error is None``. Each response is
    wrapped in a ``<model>`` tag with provider and model_id attributes.

    Args:
        responses: All model responses (including failures).
        original_prompt: The original user prompt (unused in output but
            available for future extensions).
        original_context: The original context (unused in output but
            available for future extensions).

    Returns:
        Formatted XML string of successful responses.
    """
    parts: list[str] = []
    for r in responses:
        if r.error is None:
            # Escape provider/model_id to prevent attribute injection,
            # and escape content to prevent tag injection (model impersonation)
            safe_provider = html_escape(r.provider, quote=True)
            safe_model_id = html_escape(r.model_id, quote=True)
            safe_content = html_escape(r.content, quote=False)
            source_attr = f' source="{html_escape(r.source, quote=True)}"'
            parts.append(
                f'<model provider="{safe_provider}" model_id="{safe_model_id}"{source_attr}>\n'
                f"{safe_content}\n"
                f"</model>"
            )
    return "\n\n".join(parts)


def parse_aggregation_output(raw: str) -> dict:
    """Extract structured JSON from the aggregator's raw response.

    The response may contain JSON directly, or JSON wrapped in a markdown
    code block (```json ... ```). Falls back to treating the entire raw
    text as the synthesis if JSON extraction fails.

    Args:
        raw: The raw text response from the aggregator model.

    Returns:
        A dict with keys: synthesis, agreements, disagreements,
        unique_findings.
    """
    expected_keys = {"synthesis", "agreements", "disagreements", "unique_findings"}

    # Try to find JSON object in the text
    # First, try stripping markdown code fences
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if code_block_match:
        candidate = code_block_match.group(1).strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and expected_keys.issubset(parsed.keys()):
                return parsed
        except json.JSONDecodeError:
            pass

    # Try to find a raw JSON object using raw_decode (avoids greedy matching)
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch == '{':
            try:
                parsed, _ = decoder.raw_decode(raw, i)
                if isinstance(parsed, dict) and expected_keys.issubset(parsed.keys()):
                    return parsed
            except json.JSONDecodeError:
                continue

    # Fallback: treat entire raw text as synthesis
    return {
        "synthesis": raw,
        "agreements": [],
        "disagreements": [],
        "unique_findings": [],
    }


async def aggregate(
    responses: list[ModelResponse],
    prompt: str,
    context: str,
    mode: str,
    config: ConsensusConfig,
    prompts_dir: str,
    aggregator_provider: BaseProvider | None = None,
) -> ConsensusResult:
    """Aggregate multi-model responses into a consensus result.

    Args:
        responses: Responses from all queried models.
        prompt: The original user prompt.
        context: The original context sent to models.
        mode: The consensus mode (e.g. "review").
        config: The consensus configuration.
        prompts_dir: Directory containing aggregation prompt templates.
        aggregator_provider: Optional provider for the aggregation call.
            If not provided, creates a provider from the first
            configured model.

    Returns:
        A fully populated ConsensusResult.
    """
    # Build per_model from ALL responses (including failures)
    per_model = [
        {
            "provider": r.provider,
            "model_id": r.model_id,
            "responded": r.error is None,
            "latency_ms": r.latency_ms,
        }
        for r in responses
    ]

    successful = [r for r in responses if r.error is None]
    models_queried = len(responses)
    models_responded = len(successful)

    # Determine status
    if models_responded == models_queried:
        status = "complete"
    elif models_responded >= config.min_models:
        status = "partial"
    else:
        return ConsensusResult(
            status="unavailable",
            models_queried=models_queried,
            models_responded=models_responded,
            per_model=per_model,
            error=f"Too few models responded: {models_responded}/{models_queried} (min_models={config.min_models})",
        )

    # Load the mode-specific aggregation prompt
    try:
        template = load_aggregation_prompt(mode, prompts_dir)
    except AggregationError as e:
        return ConsensusResult(
            status="unavailable",
            models_queried=models_queried,
            models_responded=models_responded,
            per_model=per_model,
            error=f"Aggregation prompt not found: {e}",
        )

    # Substitute placeholders
    model_responses_xml = build_aggregation_input(responses, prompt, context)
    aggregation_prompt = template.replace("[MODEL_RESPONSES]", model_responses_xml)
    aggregation_prompt = aggregation_prompt.replace("[ORIGINAL_CONTEXT]", context)

    # Create or use provided aggregator provider
    if aggregator_provider is None:
        if not config.models:
            return ConsensusResult(
                status="unavailable",
                models_queried=models_queried,
                models_responded=models_responded,
                per_model=per_model,
                error="No models configured for aggregation",
            )
        aggregator_provider = create_provider(config.models[0])

    # Call the aggregator
    try:
        agg_response = await aggregator_provider.query(aggregation_prompt, "")
        if agg_response.error is not None:
            return ConsensusResult(
                status="unavailable",
                models_queried=models_queried,
                models_responded=models_responded,
                per_model=per_model,
                error=f"Aggregator call failed: {agg_response.error}",
            )
    except Exception as e:
        return ConsensusResult(
            status="unavailable",
            models_queried=models_queried,
            models_responded=models_responded,
            per_model=per_model,
            error=f"Aggregator exception: {type(e).__name__}",
        )

    # Parse the aggregation output
    parsed = parse_aggregation_output(agg_response.content)

    return ConsensusResult(
        status=status,
        models_queried=models_queried,
        models_responded=models_responded,
        synthesis=parsed.get("synthesis", ""),
        agreements=parsed.get("agreements", []),
        disagreements=parsed.get("disagreements", []),
        unique_findings=parsed.get("unique_findings", []),
        per_model=per_model,
    )
