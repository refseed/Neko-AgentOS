from __future__ import annotations


TOKEN_PRICE_PER_1K = {
    "small": 0.10,
    "medium": 0.50,
    "large": 2.00,
}


def estimate_cost_usd(model_tier: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate request cost by model tier."""

    rate = TOKEN_PRICE_PER_1K.get(model_tier, TOKEN_PRICE_PER_1K["small"])
    return round(((input_tokens + output_tokens) / 1000.0) * rate, 6)
