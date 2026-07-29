import os
from datetime import datetime, timedelta, timezone

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


def _is_crypto(symbol: str) -> bool:
    return "/" in symbol


class AlpacaClient:
    def __init__(self):
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
        paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

        self.trading = TradingClient(api_key, secret_key, paper=paper)
        self.stock_data = StockHistoricalDataClient(api_key, secret_key)
        self.crypto_data = CryptoHistoricalDataClient(api_key, secret_key)

    def account(self):
        return self.trading.get_account()

    def recent_bars(self, symbol: str, minutes: int = 30):
        start = datetime.now(timezone.utc) - timedelta(minutes=minutes + 5)
        if _is_crypto(symbol):
            request = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=start,
                limit=minutes,
            )
            bars = self.crypto_data.get_crypto_bars(request)
        else:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Minute,
                start=start,
                limit=minutes,
            )
            bars = self.stock_data.get_stock_bars(request)
        try:
            return bars[symbol]
        except KeyError:
            return []

    def get_position(self, symbol: str):
        target = symbol.replace("/", "")
        for position in self.trading.get_all_positions():
            if position.symbol.replace("/", "") == target:
                return position
        return None

    def open_position_qty(self, symbol: str) -> float:
        position = self.get_position(symbol)
        return float(position.qty) if position else 0.0

    def total_deployed_notional(self) -> float:
        return sum(float(p.market_value) for p in self.trading.get_all_positions())

    def buy_notional(self, symbol: str, notional: float):
        request = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC if _is_crypto(symbol) else TimeInForce.DAY,
        )
        return self.trading.submit_order(order_data=request)

    def close_position(self, symbol: str):
        return self.trading.close_position(symbol.replace("/", ""))
