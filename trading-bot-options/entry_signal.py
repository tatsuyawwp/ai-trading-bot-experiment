from dataclasses import dataclass

# Options data in Alpaca's paper environment runs ~15min delayed, so a
# short (1-min) momentum signal like the crypto/equities bots use is
# meaningless here - by the time we'd act, the underlying could easily
# have moved past our signal. A multi-hour lookback makes the delay a
# rounding error instead of the dominant source of noise.
# Values from the 2026-07-27 Gemini consult on options entry design.
LOOKBACK_MINUTES = 240
DEVIATION_THRESHOLD = 0.005  # 0.5% move over the lookback window


@dataclass
class Signal:
    symbol: str
    direction: str  # "call" | "put" | "hold"
    reason: str
    price: float
    deviation: float = 0.0


@dataclass
class Decision:
    symbol: str  # option contract symbol when trading, underlying symbol on plain "hold"/"error"
    action: str  # "buy" | "sell" | "hold" | "error"
    reason: str
    price: float  # premium for option trades, underlying price for hold rows
    underlying: str = ""
    dte: int | None = None
    bid: float | None = None  # held-position quote at decision time; None for entry-signal rows
    ask: float | None = None


def decide(symbol: str, bars) -> Signal:
    if len(bars) < 3:
        return Signal(symbol, "hold", "not enough bars yet", bars[-1].close if bars else 0)

    reference_price = bars[0].open
    current_price = bars[-1].close
    deviation = (current_price - reference_price) / reference_price

    if deviation > DEVIATION_THRESHOLD:
        return Signal(symbol, "call", f"deviation={deviation:.4f} over {LOOKBACK_MINUTES}min", current_price, deviation)

    if deviation < -DEVIATION_THRESHOLD:
        return Signal(symbol, "put", f"deviation={deviation:.4f} over {LOOKBACK_MINUTES}min", current_price, deviation)

    return Signal(symbol, "hold", f"deviation={deviation:.4f} below threshold", current_price, deviation)
