from dataclasses import dataclass
from statistics import pstdev

DEVIATION_THRESHOLD = 0.01  # 1.0% move from window open - must clear round-trip fee/spread cost (~0.8-1.0%)
MIN_MOMENTUM = 0.0015  # 0.15% last-bar move, same direction as deviation


@dataclass
class Decision:
    symbol: str
    action: str  # "buy" | "sell" | "hold"
    reason: str
    price: float
    deviation: float = 0.0
    momentum: float = 0.0
    volatility: float = 0.0


def decide(symbol: str, bars) -> Decision:
    if len(bars) < 3:
        return Decision(symbol, "hold", "not enough bars yet", bars[-1].close if bars else 0)

    reference_price = bars[0].open
    current_price = bars[-1].close
    deviation = (current_price - reference_price) / reference_price
    momentum = (bars[-1].close - bars[-2].close) / bars[-2].close
    volatility = pstdev(bar.close for bar in bars) / reference_price

    if deviation > DEVIATION_THRESHOLD and momentum > MIN_MOMENTUM:
        reason = f"deviation={deviation:.4f} momentum={momentum:.4f} vol={volatility:.4f}"
        return Decision(symbol, "buy", reason, current_price, deviation, momentum, volatility)

    if deviation < -DEVIATION_THRESHOLD and momentum < -MIN_MOMENTUM:
        reason = f"deviation={deviation:.4f} momentum={momentum:.4f} vol={volatility:.4f}"
        return Decision(symbol, "sell", reason, current_price, deviation, momentum, volatility)

    return Decision(symbol, "hold", f"deviation={deviation:.4f} below threshold", current_price, deviation, momentum, volatility)
