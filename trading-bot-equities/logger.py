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
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": decision.symbol,
        "action": decision.action,
        "reason": decision.reason,
        "price": decision.price,
        "deviation": decision.deviation,
        "momentum": decision.momentum,
        "volatility": decision.volatility,
        "side": decision.side,
        "rsi": decision.rsi,
        "bb_upper": decision.bb_upper,
        "bb_mid": decision.bb_mid,
        "bb_lower": decision.bb_lower,
        "qty": qty,
        "unrealized_plpc": unrealized_plpc,
        "equity": equity,
        "order_id": order_id,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
