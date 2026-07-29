import os
from datetime import datetime, timedelta, timezone

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import GetCalendarRequest, MarketOrderRequest

OPEN_NOISE_WINDOW = timedelta(minutes=30)
CLOSE_NOISE_WINDOW = timedelta(minutes=15)


class AlpacaClient:
    def __init__(self) -> None:
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
        paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

        self.trading = TradingClient(api_key, secret_key, paper=paper)
        self.stock_data = StockHistoricalDataClient(api_key, secret_key)

    def account(self):
        return self.trading.get_account()

    def market_window_ok(self) -> bool:
        """Market is open and outside the open/close noise windows."""
        clock = self.trading.get_clock()
        if not clock.is_open:
            return False

        calendar = self.trading.get_calendar(
            GetCalendarRequest(start=clock.timestamp.date(), end=clock.timestamp.date())
        )
        if not calendar:
            return False

        session_open = calendar[0].open.replace(tzinfo=clock.timestamp.tzinfo)
        since_open = clock.timestamp - session_open
        until_close = clock.next_close - clock.timestamp
        return since_open >= OPEN_NOISE_WINDOW and until_close >= CLOSE_NOISE_WINDOW

    def recent_bars(self, symbol: str, minutes: int = 30, timeframe: TimeFrame = TimeFrame.Minute, limit: int | None = None):
        start = datetime.now(timezone.utc) - timedelta(minutes=minutes + 5)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
            limit=limit or minutes,
        )
        bars = self.stock_data.get_stock_bars(request)
        try:
            return bars[symbol]
        except KeyError:
            return []

    def get_position(self, symbol: str):
        for position in self.trading.get_all_positions():
            if position.symbol == symbol:
                return position
        return None

    def open_position_qty(self, symbol: str) -> float:
        position = self.get_position(symbol)
        return float(position.qty) if position else 0.0

    def total_deployed_notional(self) -> float:
        """Long-side exposure only, feeding the long watchlist's own
        MAX_TOTAL_NOTIONAL budget. Deliberately excludes shorts: with
        MAX_TOTAL_NOTIONAL at $40 and a single XLF/EEM share costing
        $45-60, folding short exposure into this figure would let one
        short position alone block every long buy as a side effect.
        """
        return sum(float(p.market_value) for p in self.trading.get_all_positions() if p.side == "long")

    def total_account_exposure(self) -> float:
        """Combined long+short exposure, for the short side's own
        MAX_TOTAL_EXPOSURE check (the shared $100 pot the owner described).
        abs() matters here: Alpaca reports a short's market_value as
        negative, and a signed sum would let it cancel out long exposure
        instead of adding to it.
        """
        return sum(abs(float(p.market_value)) for p in self.trading.get_all_positions())

    def buy_notional(self, symbol: str, notional: float):
        request = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        return self.trading.submit_order(order_data=request)

    def sell_short(self, symbol: str, qty: int):
        """Opens a short (Alpaca has no notional/fractional order type for
        shorting, so this is always whole shares)."""
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.trading.submit_order(order_data=request)

    def is_shortable(self, symbol: str) -> bool:
        asset = self.trading.get_asset(symbol)
        return bool(asset.shortable and asset.easy_to_borrow)

    def time_until_close(self) -> timedelta:
        clock = self.trading.get_clock()
        return clock.next_close - clock.timestamp

    def market_minutes_elapsed(self, since: datetime) -> float:
        """Market-open minutes between `since` and now, skipping nights and
        weekends. Used for time-stop bar counts - a raw wall-clock diff
        would treat an overnight or weekend gap as elapsed trading bars and
        force-close a position the moment the market reopens, regardless
        of what actually happened during the gap.
        """
        now = datetime.now(timezone.utc)
        if since >= now:
            return 0.0

        exchange_tz = self.trading.get_clock().timestamp.tzinfo
        calendar = self.trading.get_calendar(
            GetCalendarRequest(start=since.date(), end=now.date())
        )

        total_minutes = 0.0
        for session in calendar:
            session_open = session.open.replace(tzinfo=exchange_tz)
            session_close = session.close.replace(tzinfo=exchange_tz)
            overlap_start = max(session_open, since)
            overlap_end = min(session_close, now)
            if overlap_end > overlap_start:
                total_minutes += (overlap_end - overlap_start).total_seconds() / 60
        return total_minutes

    def close_position(self, symbol: str):
        return self.trading.close_position(symbol)
