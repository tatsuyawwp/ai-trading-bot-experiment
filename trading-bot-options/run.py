import os

from dotenv import load_dotenv

from alpaca_client import AlpacaClient, parse_expiration
from entry_signal import LOOKBACK_MINUTES, Decision, decide
from logger import log_decision

load_dotenv()

TAKE_PROFIT_PCT = float(os.environ.get("TAKE_PROFIT_PCT", "0.50"))
STOP_LOSS_PCT = float(os.environ.get("STOP_LOSS_PCT", "0.30"))
FORCE_CLOSE_DTE = int(os.environ.get("FORCE_CLOSE_DTE", "21"))
MAX_PREMIUM_PER_CONTRACT = float(os.environ.get("MAX_PREMIUM_PER_CONTRACT", "300"))
MAX_TOTAL_PREMIUM_DEPLOYED = float(os.environ.get("MAX_TOTAL_PREMIUM_DEPLOYED", "500"))
CIRCUIT_BREAKER_LOSS = float(os.environ.get("CIRCUIT_BREAKER_LOSS", "100"))
BASELINE_PATH = os.path.join(os.path.dirname(__file__), "logs", "baseline_equity.txt")


def get_baseline_equity(current_equity: float) -> float:
    if os.path.exists(BASELINE_PATH):
        with open(BASELINE_PATH) as f:
            return float(f.read().strip())
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        f.write(str(current_equity))
    return current_equity


def handle_open_position(client: AlpacaClient, underlying: str, position, equity: float) -> None:
    plpc = float(position.unrealized_plpc)
    # Recorded alongside every exit/hold decision so a later Check-phase
    # review can tell a wide bid/ask spread apart from a genuine price move
    # between 5-min cycles (see 2026-07-29 Gemini consult on a stop-loss
    # that slipped from -30% to -42.42% between two checks).
    bid, ask = client.option_quote(position.symbol)

    try:
        dte = (parse_expiration(position.symbol) - client.exchange_today()).days
    except ValueError as e:
        # Can't verify how close this position is to expiry/auto-exercise -
        # the whole point of the DTE guard is to prevent that risk, so an
        # unparseable symbol is itself a fail-safe trigger to close now
        # rather than silently skipping this position forever.
        order = client.close_position(position.symbol)
        decision = Decision(position.symbol, "sell", f"fail-safe close - could not parse expiration: {e}",
                             float(position.current_price), underlying, bid=bid, ask=ask)
        log_decision(decision, qty=float(position.qty), order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
        print(f"{position.symbol}: sell - fail-safe close (unparseable expiration)")
        return

    if dte <= FORCE_CLOSE_DTE:
        order = client.close_position(position.symbol)
        decision = Decision(position.symbol, "sell", f"DTE{dte} forced close (auto-exercise guard)",
                             float(position.current_price), underlying, dte, bid=bid, ask=ask)
        log_decision(decision, qty=float(position.qty), order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
        print(f"{position.symbol}: sell - DTE{dte} forced close")
        return

    if plpc <= -STOP_LOSS_PCT:
        order = client.close_position(position.symbol)
        decision = Decision(position.symbol, "sell", f"stop-loss triggered ({plpc * 100:.2f}%)",
                             float(position.current_price), underlying, dte, bid=bid, ask=ask)
        log_decision(decision, qty=float(position.qty), order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
        print(f"{position.symbol}: sell - stop-loss triggered ({plpc * 100:.2f}%)")
        return

    if plpc >= TAKE_PROFIT_PCT:
        order = client.close_position(position.symbol)
        decision = Decision(position.symbol, "sell", f"take-profit triggered (+{plpc * 100:.2f}%)",
                             float(position.current_price), underlying, dte, bid=bid, ask=ask)
        log_decision(decision, qty=float(position.qty), order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
        print(f"{position.symbol}: sell - take-profit triggered (+{plpc * 100:.2f}%)")
        return

    decision = Decision(position.symbol, "hold", f"holding, DTE{dte}", float(position.current_price), underlying, dte, bid=bid, ask=ask)
    log_decision(decision, qty=float(position.qty), unrealized_plpc=plpc, equity=equity)
    print(f"{position.symbol}: hold - DTE{dte}, unrealized {plpc * 100:+.2f}%")


def try_enter_position(client: AlpacaClient, underlying: str, equity: float, deployed: float) -> float:
    """Attempts one entry; returns the (possibly updated) total premium deployed
    this cycle, so the caller can enforce the shared budget cap across symbols
    processed later in the same pass."""
    bars = client.recent_underlying_bars(underlying, minutes=LOOKBACK_MINUTES)
    signal = decide(underlying, bars)

    if signal.direction == "hold":
        decision = Decision(underlying, "hold", signal.reason, signal.price, underlying)
        log_decision(decision, equity=equity)
        print(f"{underlying}: hold - {signal.reason}")
        return deployed

    contract = client.find_atm_contract(underlying, signal.direction, signal.price)
    if contract is None:
        decision = Decision(underlying, "hold", f"{signal.direction} signal but no contract in 30-45 DTE window",
                             signal.price, underlying)
        log_decision(decision, equity=equity)
        print(f"{underlying}: hold - no {signal.direction} contract found in DTE window")
        return deployed

    ask = client.option_ask_price(contract.symbol)
    if ask is None:
        print(f"{underlying}: hold - no quote available for {contract.symbol}")
        return deployed

    premium_cost = ask * 100
    dte = (contract.expiration_date - client.exchange_today()).days

    if premium_cost > MAX_PREMIUM_PER_CONTRACT:
        decision = Decision(contract.symbol, "hold", f"skipped - premium ${premium_cost:.2f} exceeds ${MAX_PREMIUM_PER_CONTRACT} cap",
                             ask, underlying, dte)
        log_decision(decision, equity=equity)
        print(f"{contract.symbol}: skipped - premium ${premium_cost:.2f} exceeds ${MAX_PREMIUM_PER_CONTRACT} cap")
        return deployed

    if deployed + premium_cost > MAX_TOTAL_PREMIUM_DEPLOYED:
        decision = Decision(contract.symbol, "hold", f"skipped - would exceed ${MAX_TOTAL_PREMIUM_DEPLOYED} pretend budget",
                             ask, underlying, dte)
        log_decision(decision, equity=equity)
        print(f"{contract.symbol}: skipped - would exceed ${MAX_TOTAL_PREMIUM_DEPLOYED} pretend budget")
        return deployed

    order = client.buy_option(contract.symbol, qty=1, limit_price=ask)
    decision = Decision(contract.symbol, "buy", signal.reason, ask, underlying, dte)
    log_decision(decision, qty=1, order_id=str(order.id), equity=equity)
    print(f"{contract.symbol}: buy 1x @ ${ask:.2f} limit ({signal.direction}, DTE{dte}) - {signal.reason}")
    return deployed + premium_cost


def main():
    client = AlpacaClient()

    if not client.market_window_ok():
        print("Market closed or within open/close noise window - skipping cycle.")
        return

    watchlist = os.environ["WATCHLIST"].split(",")

    account = client.account()
    equity = float(account.equity)
    baseline = get_baseline_equity(equity)
    pretend_pl = equity - baseline
    print(f"Paper account equity: ${equity} | cash: ${account.cash} | pretend P&L: ${pretend_pl:+.2f}")

    if pretend_pl <= -CIRCUIT_BREAKER_LOSS:
        print(f"CIRCUIT BREAKER: pretend P&L ${pretend_pl:.2f} exceeds -${CIRCUIT_BREAKER_LOSS} limit. Closing all option positions and halting.")
        for position in client.get_option_positions():
            client.close_position(position.symbol)
            print(f"{position.symbol}: emergency close (circuit breaker)")
        return

    deployed = client.total_deployed_premium()
    for underlying in watchlist:
        underlying = underlying.strip()
        try:
            position = client.get_option_position(underlying)
            if position:
                handle_open_position(client, underlying, position, equity)
            else:
                deployed = try_enter_position(client, underlying, equity, deployed)
        except Exception as e:
            error_decision = Decision(underlying, "error", str(e), 0.0, underlying)
            log_decision(error_decision, equity=equity)
            print(f"{underlying}: error - {e}")


if __name__ == "__main__":
    main()
