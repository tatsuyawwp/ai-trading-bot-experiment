# Crypto Paper Trading Bot

Part of the [AI-Agent-Built Trading Bot Experiment](../README.md) — read that
file first for the full disclaimer.

## Strategy

Momentum/deviation: compares the current price to the window-open price and
to the last-bar move. Buys when price has deviated up with confirming
momentum, sells (or shorts, in the equities bot) on the mirror condition.
Runs every 5 minutes across a fixed watchlist.

- `DEVIATION_THRESHOLD = 0.01` — must clear the assumed round-trip fee/spread
  cost (~0.8-1.0% for crypto on Alpaca) before it's worth acting on.
- `MIN_MOMENTUM = 0.0015` — last-bar move must confirm the same direction as
  the deviation, to reduce reversal-into-your-entry noise.

See `strategy.py` for the exact logic.

## Setup

1. Copy `.env.example` to `.env` and fill in your own Alpaca **paper
   trading** keys (from https://app.alpaca.markets — no KYC required to
   start).
2. `pip install -r requirements.txt`
3. `python run.py`

Run it on a schedule (cron, Task Scheduler, etc.) — it does one evaluation
pass per invocation, not a long-running loop.

## Structure

- `alpaca_client.py` — thin wrapper around `alpaca-py` for auth, orders,
  positions, and bar data
- `strategy.py` — the trading logic described above
- `run.py` — entry point; one evaluation pass per watchlist symbol, with a
  stop-loss / take-profit / circuit-breaker check first
- `logger.py` — appends every decision (including holds) to
  `logs/trades.jsonl` with the full reasoning, not just fills
- `report.py` — read-only report over `logs/trades.jsonl`: win rate,
  expectancy, profit factor, MFE/MAE, per-symbol breakdown, equity
  drawdown. Safe to run anytime; never touches the bot's live state.

## Early results (informational only — not a track record)

As of this fork, the crypto bot had **zero closed round-trip trades** — every
position opened during the logged period was still open. There is no
meaningful win-rate or expectancy data yet. Do not read anything into this
beyond "the strategy rarely fires and hadn't completed a full cycle."

One real bug worth knowing about: an earlier version fed the bot bars from a
frozen/stale time window (the bars request never advanced its `start` time),
so every decision logged before `2026-07-27T06:11:00Z` was made on fake data.
`report.py` filters those rows out via `DATA_START`. This is exactly the kind
of failure this project exists to document — see the top-level README.

## Rules

- Paper trading only. No leverage, no options, no margin in this bot.
- Every trade decision is logged with its reasoning, not just the fill.
