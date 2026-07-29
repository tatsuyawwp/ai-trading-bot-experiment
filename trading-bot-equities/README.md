# Equities / ETF Paper Trading Bot

Part of the [AI-Agent-Built Trading Bot Experiment](../README.md) — read that
file first for the full disclaimer, **including the negative-expectancy
result described below.**

## Strategy

Two strategies live in this bot, deliberately decoupled so changes to one
can't affect the other:

- **Mean-reversion (`decide_mean_reversion`, long watchlist)** — Bollinger
  Bands + Wilder's RSI on 15-minute bars. Buys when price closed below the
  lower band with RSI oversold on the *previous* bar, then reverses up on the
  current bar; exits at the SMA centerline, a stop-loss/take-profit, or a
  time-stop (a position that hasn't reverted within N bars). This replaced
  an earlier momentum-chasing approach for the long side.
- **Momentum (`decide`, short watchlist)** — the same deviation/momentum
  logic as the [crypto bot](../trading-bot), applied to the short side. Left
  untouched so it can't interact with the newer mean-reversion code.

ETFs (`SPY`, `QQQ`, `XLF`, `EEM`) use tighter thresholds than single names —
they move less over the same window.

## Short-selling (dormant by default)

The short-selling code path exists but does nothing unless you explicitly
set `SHORT_WATCHLIST` in `.env`. It's isolated from the long watchlist so a
long signal and a short signal can never collide on the same ticker, and it
force-closes any open short 15 minutes before market close regardless of
other checks (overnight gap risk on a short is unbounded). If you enable it,
understand that Alpaca's shortable/easy-to-borrow status can change without
notice, and that `MAX_TOTAL_EXPOSURE` is a shared long+short cap, not
per-side.

## Setup

1. Copy `.env.example` to `.env` and fill in your own Alpaca **paper
   trading** keys.
2. `pip install -r requirements.txt`
3. `python run.py`

Run it on a schedule during market hours — it skips cycles automatically
outside the open/close noise windows or when the market is closed.

## Structure

- `alpaca_client.py` — Alpaca wrapper: auth, orders, positions, market
  calendar/clock helpers, long vs. short exposure accounting
- `strategy.py` — both strategies described above
- `run.py` — entry point: circuit breaker check, forced short close-out
  before the bell, short watchlist handling, then the long/mean-reversion
  loop with stop-loss / take-profit / time-stop
- `logger.py` — appends every decision to `logs/trades.jsonl`, including
  RSI/Bollinger Band values and long/short side
- `report.py` — read-only report over `logs/trades.jsonl` (win rate,
  expectancy, profit factor, MFE/MAE, per-symbol breakdown, equity
  drawdown). Safe to run anytime.

## Early results — original strategy showed negative expectancy

**This is the honest result, not a cherry-picked one.** Over the first
logged period (4 closed round-trip trades — a genuinely small sample, so
treat this as a signal to keep testing rather than a final verdict):

- Win rate: 25% (1 win, 3 losses)
- Expectancy: **-0.46% per trade**
- Profit factor: 0.02 (near-total loss of gross profit to gross loss)

In other words, the original momentum-based approach on equities lost money
more often than it made money, and the losses were larger than the wins.
That's a large part of why the mean-reversion strategy above was built to
replace it for the long watchlist — this repo intentionally keeps both the
failure and the redesign visible rather than quietly overwriting history.

**Do not treat either strategy as proven.** Four trades is not a track
record. Re-run `report.py` yourself against your own data before drawing any
conclusion.

## Rules

- Paper trading only. Every decision is logged with its reasoning.
