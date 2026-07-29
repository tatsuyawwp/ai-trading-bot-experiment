import json
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from alpaca_client import AlpacaClient
from logger import log_decision
from strategy import Decision, decide, decide_mean_reversion, mean_reversion_params_for, MEAN_REVERSION_BAR_MINUTES, MEAN_REVERSION_LOOKBACK_MINUTES, MEAN_REVERSION_BAR_LIMIT
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

load_dotenv()

PER_TRADE_NOTIONAL = float(os.environ.get("PER_TRADE_NOTIONAL", "20"))
MAX_TOTAL_NOTIONAL = float(os.environ.get("MAX_TOTAL_NOTIONAL", "40"))
CIRCUIT_BREAKER_LOSS = float(os.environ.get("CIRCUIT_BREAKER_LOSS", "20"))
BASELINE_PATH = os.path.join(os.path.dirname(__file__), "logs", "baseline_equity.txt")
POSITION_OPENED_AT_PATH = os.path.join(os.path.dirname(__file__), "logs", "position_opened_at.json")
MEAN_REVERSION_TIMEFRAME = TimeFrame(MEAN_REVERSION_BAR_MINUTES, TimeFrameUnit.Minute)

# Short-selling (added 2026-07-29, dormant until SHORT_WATCHLIST is set in
# .env). Deliberately a separate symbol universe from WATCHLIST so a long
# signal and a short signal can never collide on the same ticker.
SHORT_WATCHLIST = [s.strip() for s in os.environ.get("SHORT_WATCHLIST", "").split(",") if s.strip()]
SHORT_STOP_LOSS_PCT = float(os.environ.get("SHORT_STOP_LOSS_PCT", "0.04"))
SHORT_TAKE_PROFIT_PCT = float(os.environ.get("SHORT_TAKE_PROFIT_PCT", "0.07"))
MAX_CONCURRENT_SHORTS = int(os.environ.get("MAX_CONCURRENT_SHORTS", "1"))
MAX_TOTAL_EXPOSURE = float(os.environ.get("MAX_TOTAL_EXPOSURE", "100"))
# Shorts get force-closed once we're this close to the bell, independent of
# market_window_ok() (which would otherwise skip the whole cycle here) -
# overnight gap risk is unbounded for a short position.
SHORT_FORCE_CLOSE_WINDOW = timedelta(minutes=15)


def get_baseline_equity(current_equity: float) -> float:
    if os.path.exists(BASELINE_PATH):
        with open(BASELINE_PATH) as f:
            return float(f.read().strip())
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        f.write(str(current_equity))
    return current_equity


def _load_opened_at() -> dict:
    if os.path.exists(POSITION_OPENED_AT_PATH):
        with open(POSITION_OPENED_AT_PATH) as f:
            return json.load(f)
    return {}


def _save_opened_at(data: dict) -> None:
    os.makedirs(os.path.dirname(POSITION_OPENED_AT_PATH), exist_ok=True)
    with open(POSITION_OPENED_AT_PATH, "w") as f:
        json.dump(data, f)


def mark_position_opened(symbol: str) -> None:
    data = _load_opened_at()
    data[symbol] = datetime.now(timezone.utc).isoformat()
    _save_opened_at(data)


def mark_position_closed(symbol: str) -> None:
    data = _load_opened_at()
    if data.pop(symbol, None) is not None:
        _save_opened_at(data)


def bars_elapsed_since_open(client: AlpacaClient, symbol: str, bar_minutes: int) -> float | None:
    """None means we have no record of when this position opened (e.g. the
    bot was restarted, or the position predates this feature) - callers
    should treat that as "not enough info to time-stop" rather than 0.
    """
    opened_at_str = _load_opened_at().get(symbol)
    if not opened_at_str:
        return None
    opened_at = datetime.fromisoformat(opened_at_str)
    return client.market_minutes_elapsed(opened_at) / bar_minutes


def force_close_shorts_before_bell(client: AlpacaClient, equity: float) -> None:
    """Safety-critical: a short left open overnight has unbounded gap risk,
    so each symbol is isolated with its own try/except - one symbol's order
    failure must not stop the rest of the short book from being flattened
    before the bell.
    """
    if not SHORT_WATCHLIST:
        return
    if client.time_until_close() > SHORT_FORCE_CLOSE_WINDOW:
        return
    for symbol in SHORT_WATCHLIST:
        try:
            position = client.get_position(symbol)
            if position and position.side == "short":
                plpc = float(position.unrealized_plpc)
                order = client.close_position(symbol)
                decision = Decision(symbol, "buy", "forced close - approaching market close (overnight gap guard)",
                                     float(position.current_price), side="short")
                log_decision(decision, qty=float(position.qty), order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
                print(f"{symbol}: forced close before market close (short)")
        except Exception as e:
            error_decision = Decision(symbol, "error", str(e), 0.0, side="short")
            log_decision(error_decision, equity=equity)
            print(f"{symbol}: error during pre-close force-close - {e} (short)")


def handle_short_watchlist(client: AlpacaClient, equity: float) -> None:
    try:
        open_shorts = sum(
            1 for s in SHORT_WATCHLIST
            if (p := client.get_position(s)) and p.side == "short"
        )
    except Exception as e:
        print(f"short watchlist: error counting open shorts - {e}, skipping this cycle")
        return

    for symbol in SHORT_WATCHLIST:
        try:
            position = client.get_position(symbol)
            held_qty = float(position.qty) if position else 0.0
            is_short = bool(position and position.side == "short")
            plpc = float(position.unrealized_plpc) if position else None

            if is_short:
                # Covering a short is a buy order at the broker regardless of
                # trigger reason - action must say "buy" here (not "sell",
                # which is what *opening* the short logged) so report.py can
                # tell an open from a close when it's later made side-aware.
                if plpc <= -SHORT_STOP_LOSS_PCT:
                    order = client.close_position(symbol)
                    decision = Decision(symbol, "buy", f"stop-loss triggered ({plpc * 100:.2f}%)",
                                         float(position.current_price), side="short")
                    log_decision(decision, qty=held_qty, order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
                    print(f"{symbol}: cover - stop-loss triggered ({plpc * 100:.2f}%)")
                    continue

                if plpc >= SHORT_TAKE_PROFIT_PCT:
                    order = client.close_position(symbol)
                    decision = Decision(symbol, "buy", f"take-profit triggered (+{plpc * 100:.2f}%)",
                                         float(position.current_price), side="short")
                    log_decision(decision, qty=held_qty, order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
                    print(f"{symbol}: cover - take-profit triggered (+{plpc * 100:.2f}%)")
                    continue

            bars = client.recent_bars(symbol)
            decision = decide(symbol, bars, side="short")

            order_id = None
            if decision.action == "sell" and held_qty == 0:
                if open_shorts >= MAX_CONCURRENT_SHORTS:
                    print(f"{symbol}: short skipped - already at {MAX_CONCURRENT_SHORTS} concurrent short position(s)")
                elif not client.is_shortable(symbol):
                    print(f"{symbol}: short skipped - not shortable/easy-to-borrow right now")
                elif client.total_account_exposure() + decision.price > MAX_TOTAL_EXPOSURE:
                    print(f"{symbol}: short skipped - would exceed ${MAX_TOTAL_EXPOSURE} combined long+short exposure")
                else:
                    order = client.sell_short(symbol, qty=1)
                    order_id = str(order.id)
                    open_shorts += 1
            elif decision.action == "buy" and is_short:
                order = client.close_position(symbol)
                order_id = str(order.id)

            log_decision(decision, qty=held_qty, order_id=order_id, unrealized_plpc=plpc, equity=equity)
            print(f"{symbol}: {decision.action} - {decision.reason} (short)")
        except Exception as e:
            error_decision = Decision(symbol, "error", str(e), 0.0, side="short")
            log_decision(error_decision, equity=equity)
            print(f"{symbol}: error - {e} (short)")


def main():
    client = AlpacaClient()

    account = client.account()
    equity = float(account.equity)

    # Runs even when the cycle is otherwise skipped below (open/close noise
    # windows and full market-closed both return early) - unlike a long
    # position, a short left open overnight has unbounded gap risk. A
    # failure here must not prevent the long-only checks further down.
    try:
        force_close_shorts_before_bell(client, equity)
    except Exception as e:
        print(f"force_close_shorts_before_bell: error - {e}")

    if not client.market_window_ok():
        print("Market closed or within open/close noise window - skipping cycle.")
        return

    watchlist = os.environ["WATCHLIST"].split(",")

    baseline = get_baseline_equity(equity)
    pretend_pl = equity - baseline
    print(f"Paper account equity: ${equity} | cash: ${account.cash} | pretend P&L: ${pretend_pl:+.2f}")

    if pretend_pl <= -CIRCUIT_BREAKER_LOSS:
        print(f"CIRCUIT BREAKER: pretend P&L ${pretend_pl:.2f} exceeds -${CIRCUIT_BREAKER_LOSS} limit. Closing all positions and halting.")
        for symbol in watchlist + SHORT_WATCHLIST:
            symbol = symbol.strip()
            position = client.get_position(symbol)
            if position:
                client.close_position(symbol)
                mark_position_closed(symbol)  # no-op for SHORT_WATCHLIST symbols, which don't use the sidecar
                print(f"{symbol}: emergency close (circuit breaker)")
        return

    handle_short_watchlist(client, equity)

    for symbol in watchlist:
        symbol = symbol.strip()
        try:
            params = mean_reversion_params_for(symbol)
            position = client.get_position(symbol)
            held_qty = float(position.qty) if position else 0.0
            plpc = float(position.unrealized_plpc) if position else None

            if position and plpc <= -params["stop_loss_pct"]:
                order = client.close_position(symbol)
                loss_pct = plpc * 100
                decision = Decision(symbol, "sell", f"stop-loss triggered ({loss_pct:.2f}%)", float(position.current_price))
                log_decision(decision, qty=held_qty, order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
                mark_position_closed(symbol)
                print(f"{symbol}: sell - stop-loss triggered ({loss_pct:.2f}%)")
                continue

            if position and plpc >= params["take_profit_pct"]:
                order = client.close_position(symbol)
                gain_pct = plpc * 100
                decision = Decision(symbol, "sell", f"take-profit triggered (+{gain_pct:.2f}%)", float(position.current_price))
                log_decision(decision, qty=held_qty, order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
                mark_position_closed(symbol)
                print(f"{symbol}: sell - take-profit triggered (+{gain_pct:.2f}%)")
                continue

            if position:
                bars_elapsed = bars_elapsed_since_open(client, symbol, MEAN_REVERSION_BAR_MINUTES)
                if bars_elapsed is None:
                    # No sidecar record - either a fresh process or a
                    # position that predates this feature (e.g. opened
                    # under the old strategy). Start the clock now rather
                    # than leaving the time-stop permanently disabled for
                    # this symbol.
                    mark_position_opened(symbol)
                    print(f"{symbol}: WARNING - no entry-time record for an open position, starting time-stop clock now")
                elif bars_elapsed >= params["time_stop_bars"]:
                    order = client.close_position(symbol)
                    decision = Decision(symbol, "sell", f"time-stop: {bars_elapsed:.1f} bars ({MEAN_REVERSION_BAR_MINUTES}min each) without reverting to mean",
                                         float(position.current_price))
                    log_decision(decision, qty=held_qty, order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
                    mark_position_closed(symbol)
                    print(f"{symbol}: sell - time-stop ({bars_elapsed:.1f} bars)")
                    continue

            bars = client.recent_bars(symbol, minutes=MEAN_REVERSION_LOOKBACK_MINUTES,
                                       timeframe=MEAN_REVERSION_TIMEFRAME, limit=MEAN_REVERSION_BAR_LIMIT)
            decision = decide_mean_reversion(symbol, bars)

            order_id = None
            if decision.action == "buy" and held_qty == 0:
                deployed = client.total_deployed_notional()
                if deployed + PER_TRADE_NOTIONAL > MAX_TOTAL_NOTIONAL:
                    print(f"{symbol}: buy skipped - would exceed ${MAX_TOTAL_NOTIONAL} pretend budget (${deployed:.2f} already deployed)")
                else:
                    order = client.buy_notional(symbol, PER_TRADE_NOTIONAL)
                    order_id = str(order.id)
                    mark_position_opened(symbol)
            elif decision.action == "sell" and held_qty > 0:
                order = client.close_position(symbol)
                order_id = str(order.id)
                mark_position_closed(symbol)

            log_decision(decision, qty=held_qty, order_id=order_id, unrealized_plpc=plpc, equity=equity)
            print(f"{symbol}: {decision.action} - {decision.reason}")
        except Exception as e:
            error_decision = Decision(symbol, "error", str(e), 0.0)
            log_decision(error_decision, equity=equity)
            print(f"{symbol}: error - {e}")


if __name__ == "__main__":
    main()
