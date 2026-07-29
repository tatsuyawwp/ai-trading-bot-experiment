import os

from dotenv import load_dotenv

from alpaca_client import AlpacaClient
from logger import log_decision
from strategy import Decision, decide

load_dotenv()

PER_TRADE_NOTIONAL = float(os.environ.get("PER_TRADE_NOTIONAL", "20"))
MAX_TOTAL_NOTIONAL = float(os.environ.get("MAX_TOTAL_NOTIONAL", "40"))
STOP_LOSS_PCT = float(os.environ.get("STOP_LOSS_PCT", "0.05"))
TAKE_PROFIT_PCT = float(os.environ.get("TAKE_PROFIT_PCT", "0.07"))
CIRCUIT_BREAKER_LOSS = float(os.environ.get("CIRCUIT_BREAKER_LOSS", "20"))
BASELINE_PATH = os.path.join(os.path.dirname(__file__), "logs", "baseline_equity.txt")


def get_baseline_equity(current_equity: float) -> float:
    if os.path.exists(BASELINE_PATH):
        with open(BASELINE_PATH) as f:
            return float(f.read().strip())
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        f.write(str(current_equity))
    return current_equity


def main():
    client = AlpacaClient()
    watchlist = os.environ["WATCHLIST"].split(",")

    account = client.account()
    equity = float(account.equity)
    baseline = get_baseline_equity(equity)
    pretend_pl = equity - baseline
    print(f"Paper account equity: ${equity} | cash: ${account.cash} | pretend P&L: ${pretend_pl:+.2f}")

    if pretend_pl <= -CIRCUIT_BREAKER_LOSS:
        print(f"CIRCUIT BREAKER: pretend P&L ${pretend_pl:.2f} exceeds -${CIRCUIT_BREAKER_LOSS} limit. Closing all positions and halting.")
        for symbol in watchlist:
            symbol = symbol.strip()
            position = client.get_position(symbol)
            if position:
                client.close_position(symbol)
                print(f"{symbol}: emergency close (circuit breaker)")
        return

    for symbol in watchlist:
        symbol = symbol.strip()
        try:
            position = client.get_position(symbol)
            held_qty = float(position.qty) if position else 0.0
            plpc = float(position.unrealized_plpc) if position else None

            if position and plpc <= -STOP_LOSS_PCT:
                order = client.close_position(symbol)
                loss_pct = plpc * 100
                decision = Decision(symbol, "sell", f"stop-loss triggered ({loss_pct:.2f}%)", float(position.current_price))
                log_decision(decision, qty=held_qty, order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
                print(f"{symbol}: sell - stop-loss triggered ({loss_pct:.2f}%)")
                continue

            if position and plpc >= TAKE_PROFIT_PCT:
                order = client.close_position(symbol)
                gain_pct = plpc * 100
                decision = Decision(symbol, "sell", f"take-profit triggered (+{gain_pct:.2f}%)", float(position.current_price))
                log_decision(decision, qty=held_qty, order_id=str(order.id), unrealized_plpc=plpc, equity=equity)
                print(f"{symbol}: sell - take-profit triggered (+{gain_pct:.2f}%)")
                continue

            bars = client.recent_bars(symbol)
            decision = decide(symbol, bars)

            order_id = None
            if decision.action == "buy" and held_qty == 0:
                deployed = client.total_deployed_notional()
                if deployed + PER_TRADE_NOTIONAL > MAX_TOTAL_NOTIONAL:
                    print(f"{symbol}: buy skipped - would exceed ${MAX_TOTAL_NOTIONAL} pretend budget (${deployed:.2f} already deployed)")
                else:
                    order = client.buy_notional(symbol, PER_TRADE_NOTIONAL)
                    order_id = str(order.id)
            elif decision.action == "sell" and held_qty > 0:
                order = client.close_position(symbol)
                order_id = str(order.id)

            log_decision(decision, qty=held_qty, order_id=order_id, unrealized_plpc=plpc, equity=equity)
            print(f"{symbol}: {decision.action} - {decision.reason}")
        except Exception as e:
            print(f"{symbol}: error - {e}")


if __name__ == "__main__":
    main()
