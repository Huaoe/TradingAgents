"""Estimate LLM spend from token counts."""

from __future__ import annotations

import os


def estimate_cost(tokens_in: int, tokens_out: int) -> float:
    """Return an estimated dollar spend from input/output token counts.

    Rates default to OpenAI-style tier-1 pricing and can be overridden via
    ``LLM_COST_INPUT_PER_1M`` and ``LLM_COST_OUTPUT_PER_1M``.
    """
    input_rate = float(os.getenv("LLM_COST_INPUT_PER_1M", "2.5"))
    output_rate = float(os.getenv("LLM_COST_OUTPUT_PER_1M", "10.0"))
    return (tokens_in * input_rate + tokens_out * output_rate) / 1_000_000
