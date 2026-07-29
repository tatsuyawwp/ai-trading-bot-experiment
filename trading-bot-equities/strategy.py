from dataclasses import dataclass
from statistics import pstdev

# ETFs move less than single names over the same window, so they get a
# tighter threshold; crypto's 1.0%/0.15% would almost never fire on these.
# Values from the 2026-07-27 Gemini consult on equities-specific thresholds.
# XLF/EEM (short watchlist, added 2026-07-29) are large liquid ETFs too.
ETF_SYMBOLS = {"SPY", "QQQ", "XLF", "EEM"}

THRESHOLDS = {
    "etf": {"deviation": 0.0025, "momentum": 0.0004},
    "stock": {"deviation": 0.0060, "momentum": 0.0010},
}


def _thresholds_for(symbol: str) -> dict[str, float]:
    return THRESHOLDS["etf"] if symbol in ETF_SYMBOLS else THRESHOLDS["stock"]


@dataclass
class Decision:
    symbol: str
    action: str  # "buy" | "sell" | "hold" | "error"
    reason: str
    price: float
    deviation: float = 0.0
    momentum: float = 0.0
    volatility: float = 0.0
    side: str = "long"  # "long" | "short" - which watchlist/account-side this row belongs to
    rsi: float = 0.0
    bb_upper: float = 0.0
    bb_mid: float = 0.0
    bb_lower: float = 0.0


def decide(symbol: str, bars, side: str = "long") -> Decision:
    if len(bars) < 3:
        return Decision(symbol, "hold", "not enough bars yet", bars[-1].close if bars else 0, side=side)

    reference_price = bars[0].open
    current_price = bars[-1].close
    deviation = (current_price - reference_price) / reference_price
    momentum = (bars[-1].close - bars[-2].close) / bars[-2].close
    volatility = pstdev(bar.close for bar in bars) / reference_price

    thresholds = _thresholds_for(symbol)
    dev_th = thresholds["deviation"]
    mom_th = thresholds["momentum"]

    if deviation > dev_th and momentum > mom_th:
        reason = f"deviation={deviation:.4f} momentum={momentum:.4f} vol={volatility:.4f}"
        return Decision(symbol, "buy", reason, current_price, deviation, momentum, volatility, side)

    if deviation < -dev_th and momentum < -mom_th:
        reason = f"deviation={deviation:.4f} momentum={momentum:.4f} vol={volatility:.4f}"
        return Decision(symbol, "sell", reason, current_price, deviation, momentum, volatility, side)

    return Decision(symbol, "hold", f"deviation={deviation:.4f} below threshold", current_price, deviation, momentum, volatility, side)


# --- Mean-reversion (v2, long watchlist only) ---------------------------
# Replaces the momentum-chasing decide() above for SPY/QQQ/TSLA/NVDA.
# decide() (momentum) is left untouched and still used by the short
# watchlist (XLF/EEM) - the two strategies are deliberately decoupled so
# this change can't affect the just-built, still-dormant short feature.
#
# Rationale (2026-07-29 Gemini design consult, prompted by the owner
# asking "can we out-run HFT on speed" - answer: no, a retail REST-API
# bot is ~10,000-100,000x slower than colocated HFT infrastructure, so
# the only viable edge is trading on a timescale HFT doesn't bother with).
# 15-min bars instead of 1-min: smooths out microstructure noise that a
# 1-min mean-reversion signal would mistake for a real extreme.
MEAN_REVERSION_ETF_SYMBOLS = {"SPY", "QQQ"}
MEAN_REVERSION_BAR_MINUTES = 15
MEAN_REVERSION_LOOKBACK_MINUTES = 750  # ~2 trading days of 15-min bars
MEAN_REVERSION_BAR_LIMIT = 50

STRATEGY_PARAMS = {
    "etf": {
        "bb_period": 20, "bb_std": 2.0,
        "rsi_period": 14, "rsi_oversold": 30,
        "stop_loss_pct": 0.015, "take_profit_pct": 0.03,
        "time_stop_bars": 12,
    },
    "stock": {
        "bb_period": 20, "bb_std": 2.5,
        "rsi_period": 14, "rsi_oversold": 25,
        "stop_loss_pct": 0.035, "take_profit_pct": 0.07,
        "time_stop_bars": 8,
    },
}


def mean_reversion_params_for(symbol: str) -> dict:
    # A copy, not the shared dict itself - callers only read it today, but
    # a future caller doing params["x"] = ... must not silently corrupt
    # the global default for every symbol in that class.
    params = STRATEGY_PARAMS["etf"] if symbol in MEAN_REVERSION_ETF_SYMBOLS else STRATEGY_PARAMS["stock"]
    return dict(params)


def _bollinger(closes: list[float], period: int, num_std: float) -> tuple[float, float, float] | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    sma = sum(window) / period
    std = pstdev(window)
    return sma + num_std * std, sma, sma - num_std * std  # upper, mid, lower


def _rsi(closes: list[float], period: int) -> float | None:
    """Wilder's smoothed RSI, matching the standard (non-simple-average) definition."""
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def decide_mean_reversion(symbol: str, bars) -> Decision:
    params = mean_reversion_params_for(symbol)
    min_bars = max(params["bb_period"], params["rsi_period"] + 1) + 1

    if len(bars) < min_bars:
        return Decision(symbol, "hold", f"not enough bars yet ({len(bars)}/{min_bars})", bars[-1].close if bars else 0.0)

    closes = [bar.close for bar in bars]
    current_price = closes[-1]

    prev_bb = _bollinger(closes[:-1], params["bb_period"], params["bb_std"])
    last_bb = _bollinger(closes, params["bb_period"], params["bb_std"])
    prev_rsi = _rsi(closes[:-1], params["rsi_period"])
    last_rsi = _rsi(closes, params["rsi_period"])

    if prev_bb is None or last_bb is None or prev_rsi is None or last_rsi is None:
        return Decision(symbol, "hold", "not enough bars for indicators", current_price)

    _, _, prev_lower = prev_bb
    last_upper, last_mid, last_lower = last_bb
    prev_close = closes[-2]
    last_close = closes[-1]

    is_oversold = prev_close <= prev_lower and prev_rsi <= params["rsi_oversold"]
    reversed_up = last_close > prev_close

    if is_oversold and reversed_up:
        reason = (f"mean-reversion buy: prev_close={prev_close:.2f}<=BB_lower={prev_lower:.2f} "
                  f"prev_rsi={prev_rsi:.1f}<=oversold({params['rsi_oversold']}) reversed_up")
        return Decision(symbol, "buy", reason, current_price,
                         rsi=last_rsi, bb_upper=last_upper, bb_mid=last_mid, bb_lower=last_lower)

    if last_close >= last_mid:
        reason = f"BB centerline reached: close={last_close:.2f} >= SMA{params['bb_period']}={last_mid:.2f}"
        return Decision(symbol, "sell", reason, current_price,
                         rsi=last_rsi, bb_upper=last_upper, bb_mid=last_mid, bb_lower=last_lower)

    return Decision(symbol, "hold", f"no signal, rsi={last_rsi:.1f}", current_price,
                     rsi=last_rsi, bb_upper=last_upper, bb_mid=last_mid, bb_lower=last_lower)
