import json
import os
from datetime import datetime, timezone

LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "trades.jsonl")


def log_decision(
    decision,
    qty: float = 0,
    order_id: str | None = None,
    unrealized_plpc: float | None = None,
    equity: float | None = None,
):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    mid = (decision.bid + decision.ask) / 2 if decision.bid is not None and decision.ask is not None else None
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": decision.symbol,
        "underlying": decision.underlying,
        "action": decision.action,
        "reason": decision.reason,
        "price": decision.price,
        "dte": decision.dte,
        "bid": decision.bid,
        "ask": decision.ask,
        "mid": mid,
        "qty": qty,
        "unrealized_plpc": unrealized_plpc,
        "equity": equity,
        "order_id": order_id,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
