# Options Paper Trading Bot (buy-only calls/puts)

Part of the [AI-Agent-Built Trading Bot Experiment](../README.md) — read that
file first for the full disclaimer.

## Strategy

Buy-only calls/puts (no spreads, no selling premium). For each underlying on
the watchlist:

1. Look at deviation over a 240-minute (4-hour) lookback on the underlying.
   Options quotes in Alpaca's paper environment run roughly 15 minutes
   delayed, so a short 1-minute signal (like the crypto/equities bots use)
   would be meaningless here — a multi-hour lookback makes that delay a
   rounding error instead of the dominant source of noise.
2. If deviation exceeds `DEVIATION_THRESHOLD` (0.5%), look for the
   nearest-expiry (30-45 DTE), nearest-strike-to-spot contract.
3. Buy 1 contract with a **limit** order at the currently-quoted ask (not a
   market order — see "known bug" below for why that distinction matters).

Open positions are force-closed at `FORCE_CLOSE_DTE` (default 21 days to
expiration) to avoid auto-exercise risk, in addition to the normal
stop-loss/take-profit checks.

## Setup

1. Copy `.env.example` to `.env` and fill in your own Alpaca **paper
   trading** keys. Note: options trading must be enabled on the paper
   account (a permission level you set in Alpaca's dashboard).
2. `pip install -r requirements.txt`
3. `python run.py`

## Structure

- `alpaca_client.py` — Alpaca wrapper: auth, contract search (ATM, DTE
  window), quotes, limit orders, option-position filtering by asset class
- `entry_signal.py` — the deviation-based entry signal described above
- `run.py` — entry point: circuit breaker, per-underlying entry/exit logic,
  DTE-based forced close, premium budget caps (per-contract and total)
- `logger.py` — appends every decision to `logs/trades.jsonl`, including
  bid/ask/mid at decision time
- `report.py` — read-only report over `logs/trades.jsonl` (win rate,
  expectancy, profit factor, MFE/MAE, equity drawdown). Safe to run anytime.

## Known bug worth reading: stop-loss slippage

One closed trade in this bot's early logs triggered a -30% stop-loss but
recorded a realized loss of **-42.42%** by the time the position was
actually closed. Root cause: the bot checks `unrealized_plpc` once per
5-minute cycle, and the bid/ask spread on a thinly-traded option can move
significantly between checks — the stop-loss threshold isn't a guarantee of
the exit price, especially on option premium (which is far more volatile,
percentage-wise, than the underlying). `handle_open_position()` now also
logs the bid/ask at decision time specifically so a slip like this can be
distinguished from a genuine price move after the fact.

This is exactly the kind of real failure this project exists to document —
see the top-level README.

## Early results (informational only — not a track record)

One closed trade in the logged period, the -42.42% loss described above.
That is not remotely enough data to say anything about this strategy's
expectancy — it's listed here for transparency, not as a result.

## Rules

- Paper trading only. Every decision is logged with its reasoning.
