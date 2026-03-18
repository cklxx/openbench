"""Metrics collection and calculation for agent runs."""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Model pricing table (USD per token)
# ---------------------------------------------------------------------------

# Prices are per *million* tokens – divide by 1_000_000 to get per-token cost.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-6": {"input": 5.0 / 1_000_000, "output": 25.0 / 1_000_000},
    "claude-sonnet-4-6": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "claude-haiku-4-5": {"input": 1.0 / 1_000_000, "output": 5.0 / 1_000_000},
}

# Fallback price when model is not in the table (use Sonnet pricing).
_DEFAULT_PRICING = MODEL_PRICING["claude-sonnet-4-6"]

# Rough character-to-token ratio used for estimation when the SDK does not
# expose exact token counts.
_CHARS_PER_TOKEN = 4.0


def estimate_tokens_from_text(text: str) -> int:
    """Estimate the number of tokens in *text* using a simple heuristic.

    This is intentionally conservative (~4 chars/token) and should only be
    used when the API does not return exact usage figures.
    """
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Return the estimated cost in USD for a run with the given token counts."""
    pricing = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return input_tokens * pricing["input"] + output_tokens * pricing["output"]


def get_pricing(model: str) -> dict[str, float]:
    """Return the pricing dict for *model*, falling back to default pricing."""
    return MODEL_PRICING.get(model, _DEFAULT_PRICING)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k estimator (Chen et al. 2021).

    Args:
        n: Total number of samples attempted.
        c: Number of samples that passed (correct / no error).
        k: The k in pass@k — how many attempts are considered.

    Returns:
        Estimated probability that at least one of k attempts passes.
        Returns 0.0 when n == 0 or c == 0. Returns 1.0 when all samples pass.

    Raises:
        ValueError: If k > n (cannot draw more samples than exist).
    """
    if k > n:
        raise ValueError(f"k ({k}) must be ≤ n ({n})")
    if n == 0 or c == 0:
        return 0.0
    if c == n:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)
