import os
import re
from datetime import date, datetime, timedelta, timezone

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import (
    OptionLatestQuoteRequest,
    StockBarsRequest,
    StockLatestTradeRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, ContractType, OrderSide, TimeInForce
from alpaca.trading.requests import GetCalendarRequest, GetOptionContractsRequest, LimitOrderRequest

OPEN_NOISE_WINDOW = timedelta(minutes=30)
CLOSE_NOISE_WINDOW = timedelta(minutes=15)
EXPIRY_DTE_MIN = 30
EXPIRY_DTE_MAX = 45
STRIKE_BAND_PCT = 0.08  # search +/-8% around current price for ATM candidates

# Alpaca's option symbols are ROOT + YYMMDD + C/P + strike*1000 (8 digits),
# e.g. EWZ260828C00035500. No internal padding/spaces, unlike raw OCC.
_SYMBOL_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def parse_expiration(contract_symbol: str) -> date:
    match = _SYMBOL_RE.match(contract_symbol)
    if not match:
        raise ValueError(f"unrecognized option symbol format: {contract_symbol}")
    yy, mm, dd = match.group(2)[0:2], match.group(2)[2:4], match.group(2)[4:6]
    return date(2000 + int(yy), int(mm), int(dd))


class AlpacaClient:
    def __init__(self) -> None:
        api_key = os.environ["ALPACA_API_KEY"]
        secret_key = os.environ["ALPACA_SECRET_KEY"]
        paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

        self.trading = TradingClient(api_key, secret_key, paper=paper)
        self.stock_data = StockHistoricalDataClient(api_key, secret_key)
        self.option_data = OptionHistoricalDataClient(api_key, secret_key)

    def account(self):
        return self.trading.get_account()

    def exchange_today(self) -> date:
        """Exchange-time (Alpaca clock) date, not the local machine's date.

        The local machine runs JST, and NYSE regular hours (9:30-16:00 ET)
        straddle midnight JST for most of the session - using date.today()
        here would make DTE math jitter by a day depending on what time of
        day (JST) the cron happens to fire, even within the same ET trading
        session.
        """
        return self.trading.get_clock().timestamp.date()

    def market_window_ok(self) -> bool:
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

    def underlying_price(self, symbol: str) -> float:
        trade = self.stock_data.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
        return trade[symbol].price

    def recent_underlying_bars(self, symbol: str, minutes: int):
        start = datetime.now(timezone.utc) - timedelta(minutes=minutes + 5)
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

    def find_atm_contract(self, underlying: str, option_type: str, current_price: float):
        """Nearest-expiry (30-45 DTE), nearest-strike-to-spot contract, or None."""
        today = self.exchange_today()
        band = current_price * STRIKE_BAND_PCT
        request = GetOptionContractsRequest(
            underlying_symbols=[underlying],
            expiration_date_gte=today + timedelta(days=EXPIRY_DTE_MIN),
            expiration_date_lte=today + timedelta(days=EXPIRY_DTE_MAX),
            type=ContractType.CALL if option_type == "call" else ContractType.PUT,
            strike_price_gte=f"{current_price - band:.1f}",
            strike_price_lte=f"{current_price + band:.1f}",
            limit=100,
        )
        response = self.trading.get_option_contracts(request)
        contracts = response.option_contracts
        if not contracts:
            return None

        nearest_expiry = min(c.expiration_date for c in contracts)
        same_expiry = [c for c in contracts if c.expiration_date == nearest_expiry]
        return min(same_expiry, key=lambda c: abs(float(c.strike_price) - current_price))

    def option_ask_price(self, contract_symbol: str) -> float | None:
        quote = self.option_data.get_option_latest_quote(
            OptionLatestQuoteRequest(symbol_or_symbols=contract_symbol)
        )[contract_symbol]
        return quote.ask_price if quote.ask_price is not None else None

    def option_quote(self, contract_symbol: str) -> tuple[float | None, float | None]:
        """Bid/ask for a held contract, so exit decisions can be checked
        against spread width instead of only the account's reported plpc.
        """
        quote = self.option_data.get_option_latest_quote(
            OptionLatestQuoteRequest(symbol_or_symbols=contract_symbol)
        )[contract_symbol]
        return quote.bid_price, quote.ask_price

    def get_option_positions(self):
        return [p for p in self.trading.get_all_positions() if p.asset_class == AssetClass.US_OPTION]

    def get_option_position(self, underlying: str):
        for position in self.get_option_positions():
            match = _SYMBOL_RE.match(position.symbol)
            if match and match.group(1) == underlying:
                return position
        return None

    def total_deployed_premium(self) -> float:
        return sum(float(p.cost_basis) for p in self.get_option_positions())

    def buy_option(self, contract_symbol: str, qty: int, limit_price: float):
        """Limit (not market) order: options data can run ~15min delayed in
        paper trading, so a market order could fill well above the ask we
        budget-checked against. A limit at that checked ask keeps the
        premium caps a real ceiling instead of an estimate.
        """
        request = LimitOrderRequest(
            symbol=contract_symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(limit_price, 2),
        )
        return self.trading.submit_order(order_data=request)

    def close_position(self, symbol: str):
        return self.trading.close_position(symbol)
