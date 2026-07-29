"""Phase 1 PDCA report: reads logs/trades.jsonl and prints win rate,
expectancy, profit factor, MFE/MAE, per-symbol breakdown, and equity
drawdown. Read-only, safe to run anytime; does not touch the bot.

Framework follows the Gemini consult from 2026-07-27 (session 5, consult #11).
"""

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "trades.jsonl")

# Bars were fed from a frozen stale window before this fix landed (a bug
# where the bars request never advanced its start time). Everything logged
# before this cutoff was decided on fake data and must not feed Phase 1
# analysis.
DATA_START = datetime(2026, 7, 27, 6, 11, 0, tzinfo=timezone.utc)

# Alpaca crypto round-trip fee+spread cost estimated during the threshold
# recalibration consult; not logged per-trade, so this is a fixed estimate
# used only to sanity-check whether wins are comfortably clearing costs.
ASSUMED_ROUND_TRIP_COST_PCT = 0.009

PER_TRADE_NOTIONAL = float(os.environ.get("PER_TRADE_NOTIONAL", "20"))


@dataclass
class Trade:
    symbol: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: str = ""
    realized_pl_pct: float | None = None
    mfe_pct: float = float("-inf")
    mae_pct: float = float("inf")

    @property
    def is_closed(self) -> bool:
        return self.exit_time is not None


def load_rows():
    if not os.path.exists(LOG_PATH):
        return []
    rows = []
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row["timestamp"] = datetime.fromisoformat(row["timestamp"])
            rows.append(row)
    return [r for r in rows if r["timestamp"] >= DATA_START]


def reconstruct_trades(rows) -> tuple[list[Trade], int]:
    open_trades: dict[str, Trade] = {}
    trades: list[Trade] = []
    orphaned_sells = 0

    for row in rows:
        symbol = row["symbol"]
        action = row["action"]
        filled = row["order_id"] is not None

        if action == "buy" and filled and symbol not in open_trades:
            open_trades[symbol] = Trade(symbol, row["timestamp"], row["price"])
            continue

        trade = open_trades.get(symbol)
        if trade is not None and row.get("unrealized_plpc") is not None:
            plpc = row["unrealized_plpc"]
            trade.mfe_pct = max(trade.mfe_pct, plpc)
            trade.mae_pct = min(trade.mae_pct, plpc)

        if action == "sell" and filled:
            if trade is not None:
                trade.exit_time = row["timestamp"]
                trade.exit_price = row["price"]
                trade.exit_reason = row["reason"]
                trade.realized_pl_pct = row.get("unrealized_plpc")
                trades.append(trade)
                del open_trades[symbol]
            else:
                # Entry was before DATA_START (stale-bar era) and got filtered
                # out, so this close has no matching open trade in range.
                orphaned_sells += 1

    trades.extend(open_trades.values())  # still-open positions, listed separately
    return trades, orphaned_sells


def signal_activity(rows) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        symbol, action, filled = row["symbol"], row["action"], row["order_id"] is not None
        if action == "hold":
            counts[symbol]["hold"] += 1
        elif action == "buy":
            counts[symbol]["buy_filled" if filled else "buy_skipped_budget"] += 1
        elif action == "sell":
            counts[symbol]["sell_filled" if filled else "sell_signal_no_position"] += 1
    return counts


def equity_curve(rows) -> list[tuple[datetime, float]]:
    return [(r["timestamp"], r["equity"]) for r in rows if r.get("equity") is not None]


def max_drawdown(curve: list[tuple[datetime, float]]) -> tuple[float, float]:
    if not curve:
        return 0.0, 0.0
    peak = curve[0][1]
    max_dd_abs = 0.0
    max_dd_pct = 0.0
    for _, equity in curve:
        peak = max(peak, equity)
        dd_abs = peak - equity
        dd_pct = dd_abs / peak if peak else 0.0
        max_dd_abs = max(max_dd_abs, dd_abs)
        max_dd_pct = max(max_dd_pct, dd_pct)
    return max_dd_abs, max_dd_pct


def print_report():
    rows = load_rows()
    print("=== Paper Trading Report (Phase 1) ===")
    if not rows:
        print(f"No data at/after cutoff {DATA_START.isoformat()} yet.")
        return

    print(f"Period: {rows[0]['timestamp'].isoformat()} .. {rows[-1]['timestamp'].isoformat()}")
    print(f"Cycles logged (post-bugfix cutoff): {len(rows)}")

    print("\n--- Signal activity per symbol ---")
    for symbol, counts in signal_activity(rows).items():
        parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"{symbol}: {parts}")

    trades, orphaned_sells = reconstruct_trades(rows)
    if orphaned_sells:
        print(f"\nNOTE: {orphaned_sells} sell fill(s) had no matching buy in range "
              f"(position opened before the data cutoff) and were excluded from trade stats.")
    closed = [t for t in trades if t.is_closed]
    open_trades = [t for t in trades if not t.is_closed]

    print("\n--- Trade stats (closed trades) ---")
    if not closed:
        print("Closed trades: 0 (N/A - no completed round trips yet)")
    else:
        wins = [t for t in closed if t.realized_pl_pct is not None and t.realized_pl_pct > 0]
        losses = [t for t in closed if t.realized_pl_pct is not None and t.realized_pl_pct <= 0]
        win_rate = len(wins) / len(closed)
        gross_profit = sum(t.realized_pl_pct * PER_TRADE_NOTIONAL for t in wins)
        gross_loss = sum(-t.realized_pl_pct * PER_TRADE_NOTIONAL for t in losses)
        expectancy_pct = sum(t.realized_pl_pct for t in closed) / len(closed)
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        print(f"Closed trades: {len(closed)} | wins: {len(wins)} | losses: {len(losses)}")
        print(f"Win rate: {win_rate:.1%}")
        print(f"Expectancy: {expectancy_pct:+.2%} per trade (${expectancy_pct * PER_TRADE_NOTIONAL:+.2f} at ${PER_TRADE_NOTIONAL:.0f}/trade)")
        print(f"Profit factor: {profit_factor:.2f}")
        avg_win = sum(t.realized_pl_pct for t in wins) / len(wins) if wins else 0.0
        cost_note = "clears" if avg_win > ASSUMED_ROUND_TRIP_COST_PCT else "does NOT clear"
        print(f"Avg win: {avg_win:+.2%} - {cost_note} the assumed round-trip cost ({ASSUMED_ROUND_TRIP_COST_PCT:.1%})")

        print("\n--- MFE/MAE per closed trade ---")
        for t in closed:
            print(f"{t.symbol}: entry {t.entry_time.isoformat()} -> exit {t.exit_time.isoformat()} "
                  f"| realized {t.realized_pl_pct:+.2%} | MFE {t.mfe_pct:+.2%} | MAE {t.mae_pct:+.2%} | {t.exit_reason}")

        print("\n--- Per-symbol breakdown ---")
        by_symbol = defaultdict(list)
        for t in closed:
            by_symbol[t.symbol].append(t)
        for symbol, sym_trades in by_symbol.items():
            sym_wins = [t for t in sym_trades if t.realized_pl_pct > 0]
            print(f"{symbol}: {len(sym_trades)} trades | win rate {len(sym_wins)/len(sym_trades):.1%}")

    if open_trades:
        print("\n--- Currently open positions ---")
        for t in open_trades:
            mfe = f"{t.mfe_pct:+.2%}" if t.mfe_pct != float("-inf") else "N/A"
            mae = f"{t.mae_pct:+.2%}" if t.mae_pct != float("inf") else "N/A"
            print(f"{t.symbol}: opened {t.entry_time.isoformat()} @ {t.entry_price} | MFE so far {mfe} | MAE so far {mae}")

    print("\n--- Equity ---")
    curve = equity_curve(rows)
    if not curve:
        print("N/A - no equity samples in range")
    else:
        dd_abs, dd_pct = max_drawdown(curve)
        print(f"Start equity: ${curve[0][1]:.2f} | Current equity: ${curve[-1][1]:.2f}")
        print(f"Max drawdown: ${dd_abs:.2f} ({dd_pct:.2%})")


if __name__ == "__main__":
    print_report()
