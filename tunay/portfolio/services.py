from __future__ import annotations

import datetime
from decimal import Decimal, ROUND_HALF_UP

import yfinance as yf

from tunay.portfolio.models import Asset, HistoricalPrice, Transaction

USDTRY_SYMBOL = 'USDTRY=X'
GOLD_FUTURES_SYMBOL = 'GC=F'
TROY_OUNCE_GRAMS = Decimal('31.1034768')
SUPPORTED_ASSETS = frozenset({'USD', 'GA'})
HISTORY_LOOKBACK_DAYS = 21
PRICE_QUANTUM = Decimal('0.0001')
MONEY_QUANTUM = Decimal('0.01')


class PriceFetchError(Exception):
    """Raised when a Yahoo Finance price cannot be resolved."""


class UnknownAssetError(ValueError):
    """Raised when an asset code is not supported or missing in the database."""


def _to_decimal(value: object, quantum: Decimal = PRICE_QUANTUM) -> Decimal:
    if isinstance(value, Decimal):
        number = value
    else:
        number = Decimal(str(value))
    return number.quantize(quantum, rounding=ROUND_HALF_UP)


def _require_asset_code(asset_code: str) -> str:
    if asset_code not in SUPPORTED_ASSETS:
        raise UnknownAssetError(f'Unsupported asset code: {asset_code}')
    return asset_code


def _get_asset(asset_code: str) -> Asset:
    _require_asset_code(asset_code)
    try:
        return Asset.objects.get(code=asset_code)
    except Asset.DoesNotExist as exc:
        raise UnknownAssetError(f'Asset {asset_code} is not registered') from exc


def _as_date(value: datetime.date | datetime.datetime) -> datetime.date:
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


class YFinanceFetcher:
    def fetch_price(
        self,
        asset_code: str,
        date: datetime.date | None = None,
    ) -> Decimal:
        _require_asset_code(asset_code)
        if date is None:
            return self._current_asset_price(asset_code)
        return self._historical_asset_price(asset_code, _as_date(date))

    def _current_asset_price(self, asset_code: str) -> Decimal:
        if asset_code == 'USD':
            return self._fetch_symbol_current(USDTRY_SYMBOL)
        gold_usd = self._fetch_symbol_current(GOLD_FUTURES_SYMBOL)
        usdtry = self._fetch_symbol_current(USDTRY_SYMBOL)
        return _to_decimal((gold_usd / TROY_OUNCE_GRAMS) * usdtry)

    def _historical_asset_price(self, asset_code: str, date: datetime.date) -> Decimal:
        if asset_code == 'USD':
            return self._fetch_symbol_close(USDTRY_SYMBOL, date)
        gold_usd = self._fetch_symbol_close(GOLD_FUTURES_SYMBOL, date)
        usdtry = self._fetch_symbol_close(USDTRY_SYMBOL, date)
        return _to_decimal((gold_usd / TROY_OUNCE_GRAMS) * usdtry)

    def _fetch_symbol_current(self, symbol: str) -> Decimal:
        ticker = yf.Ticker(symbol)
        try:
            last_price = ticker.fast_info.last_price
            if last_price is not None:
                return _to_decimal(last_price)
        except (KeyError, AttributeError, TypeError, ValueError):
            pass

        history = ticker.history(period='5d')
        if history.empty or 'Close' not in history:
            raise PriceFetchError(f'No current price available for {symbol}')
        return _to_decimal(history['Close'].iloc[-1])

    def _fetch_symbol_close(self, symbol: str, date: datetime.date) -> Decimal:
        start = date - datetime.timedelta(days=HISTORY_LOOKBACK_DAYS)
        end = date + datetime.timedelta(days=1)
        history = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
        if history.empty or 'Close' not in history:
            raise PriceFetchError(f'No historical price available for {symbol} on {date}')

        close = None
        for timestamp, row in history.iterrows():
            if timestamp.date() <= date:
                close = row['Close']

        if close is None:
            raise PriceFetchError(f'No market close on or before {date} for {symbol}')
        return _to_decimal(close)


class PriceService:
    def __init__(self, fetcher: YFinanceFetcher | None = None):
        self.fetcher = fetcher or YFinanceFetcher()

    def get_historical_price(self, asset_code: str, date: datetime.date) -> Decimal:
        asset = _get_asset(asset_code)
        date = _as_date(date)
        cached = HistoricalPrice.objects.filter(asset=asset, date=date).first()
        if cached is not None:
            return cached.price_try

        price = self.fetcher.fetch_price(asset_code, date)
        HistoricalPrice.objects.create(asset=asset, date=date, price_try=price)
        return price

    def get_current_price(self, asset_code: str) -> Decimal:
        _require_asset_code(asset_code)
        return self.fetcher.fetch_price(asset_code)


class TransactionService:
    def __init__(self, price_service: PriceService | None = None):
        self.price_service = price_service or PriceService()

    def create_transaction(
        self,
        asset_code: str,
        amount: Decimal,
        total_paid_try: Decimal,
        transaction_date: datetime.date,
    ) -> Transaction:
        asset = _get_asset(asset_code)
        transaction_date = _as_date(transaction_date)
        amount = _to_decimal(amount)
        total_paid_try = _to_decimal(total_paid_try, MONEY_QUANTUM)
        market_price = self.price_service.get_historical_price(asset_code, transaction_date)
        market_value = amount * market_price
        spread_fee_try = _to_decimal(
            max(Decimal('0'), total_paid_try - market_value),
            MONEY_QUANTUM,
        )
        return Transaction.objects.create(
            asset=asset,
            amount=amount,
            total_paid_try=total_paid_try,
            spread_fee_try=spread_fee_try,
            transaction_date=transaction_date,
        )


class PortfolioAnalyticsService:
    def __init__(self, price_service: PriceService | None = None):
        self.price_service = price_service or PriceService()

    def calculate_transaction_pnl(self, transaction: Transaction) -> dict[str, Decimal | None]:
        current_price = self.price_service.get_current_price(transaction.asset.code)
        current_value = _to_decimal(transaction.amount * current_price, MONEY_QUANTUM)
        pnl_try = _to_decimal(current_value - transaction.total_paid_try, MONEY_QUANTUM)
        pnl_percentage = self._pnl_percentage(pnl_try, transaction.total_paid_try)
        return {
            'current_value': current_value,
            'pnl_try': pnl_try,
            'pnl_percentage': pnl_percentage,
            'spread_fee_try': transaction.spread_fee_try,
        }

    def calculate_cumulative_pnl(self) -> dict[str, Decimal]:
        transactions = Transaction.objects.select_related('asset').all()
        total_invested = Decimal('0')
        current_total_value = Decimal('0')
        live_prices: dict[str, Decimal] = {}

        for transaction in transactions:
            total_invested += transaction.total_paid_try
            code = transaction.asset.code
            if code not in live_prices:
                live_prices[code] = self.price_service.get_current_price(code)
            current_total_value += transaction.amount * live_prices[code]

        total_invested = _to_decimal(total_invested, MONEY_QUANTUM)
        current_total_value = _to_decimal(current_total_value, MONEY_QUANTUM)
        total_pnl_try = _to_decimal(current_total_value - total_invested, MONEY_QUANTUM)
        return {
            'total_invested': total_invested,
            'current_total_value': current_total_value,
            'total_pnl_try': total_pnl_try,
            'total_pnl_percentage': self._pnl_percentage(total_pnl_try, total_invested),
        }

    @staticmethod
    def _pnl_percentage(pnl_try: Decimal, invested: Decimal) -> Decimal:
        if invested == 0:
            return Decimal('0.00')
        return _to_decimal((pnl_try / invested) * Decimal('100'), MONEY_QUANTUM)
