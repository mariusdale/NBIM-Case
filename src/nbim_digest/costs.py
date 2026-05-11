from dataclasses import dataclass


MODEL_PRICING_USD_PER_MTOK = {
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
}


@dataclass(frozen=True)
class CallCost:
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_call_cost(model: str, input_tokens: int, output_tokens: int) -> CallCost:
    pricing = MODEL_PRICING_USD_PER_MTOK.get(model, {"input": 3.0, "output": 15.0})
    cost = (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]
    return CallCost(input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=round(cost, 6))
