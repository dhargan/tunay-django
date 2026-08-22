from __future__ import annotations

import datetime
import math
from decimal import Decimal, ROUND_HALF_UP

import yfinance as yf
from django.utils import timezone

from tunay.portfolio.models import Asset, HistoricalPrice, Transaction

USDTRY_SYMBOL = 'USDTRY=X'
GOLD_FUTURES_SYMBOL = 'GC=F'
TROY_OUNCE_GRAMS = Decimal('31.1034768')
SUPPORTED_ASSETS = frozenset({'USD', 'GA'})
PRICE_QUANTUM = Decimal('0.0001')
MONEY_QUANTUM = Decimal('0.01')
INTERVAL_LOOKBACK = {
    '1m': datetime.timedelta(days=3),
    '5m': datetime.timedelta(days=5),
    '15m': datetime.timedelta(days=7),
    '1h': datetime.timedelta(days=14),
    '1d': datetime.timedelta(days=21),
}


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


def _ensure_aware(when: datetime.datetime) -> datetime.datetime:
    if timezone.is_naive(when):
        return timezone.make_aware(when)
    return when


def _cache_timestamp(when: datetime.datetime) -> datetime.datetime:
    return _ensure_aware(when).replace(second=0, microsecond=0)


def _to_utc(when: datetime.datetime) -> datetime.datetime:
    return _ensure_aware(when).astimezone(datetime.timezone.utc)


def _bar_utc(timestamp) -> datetime.datetime:
    if getattr(timestamp, 'tzinfo', None) is None:
        dt = timestamp.to_pydatetime() if hasattr(timestamp, 'to_pydatetime') else timestamp
        return dt.replace(tzinfo=datetime.timezone.utc)
    converted = timestamp.tz_convert('UTC') if hasattr(timestamp, 'tz_convert') else timestamp
    return converted.to_pydatetime()


class YFinanceFetcher:
    def fetch_price(
        self,
        asset_code: str,
        when: datetime.datetime | None = None,
    ) -> Decimal:
        _require_asset_code(asset_code)
        if when is None:
            return self._current_asset_price(asset_code)
        when = _ensure_aware(when)
        return self._historical_asset_price(asset_code, when)

    def _current_asset_price(self, asset_code: str) -> Decimal:
        if asset_code == 'USD':
            return self._fetch_symbol_current(USDTRY_SYMBOL)
        gold_usd = self._fetch_symbol_current(GOLD_FUTURES_SYMBOL)
        usdtry = self._fetch_symbol_current(USDTRY_SYMBOL)
        return _to_decimal((gold_usd / TROY_OUNCE_GRAMS) * usdtry)

    def _historical_asset_price(self, asset_code: str, when: datetime.datetime) -> Decimal:
        if asset_code == 'USD':
            return self._fetch_symbol_at(USDTRY_SYMBOL, when)
        gold_usd = self._fetch_symbol_at(GOLD_FUTURES_SYMBOL, when)
        usdtry = self._fetch_symbol_at(USDTRY_SYMBOL, when)
        return _to_decimal((gold_usd / TROY_OUNCE_GRAMS) * usdtry)

    def _fetch_symbol_current(self, symbol: str) -> Decimal:
        ticker = yf.Ticker(symbol)
        try:
            last_price = ticker.fast_info.last_price
            if last_price is not None:
                return _to_decimal(last_price)
        except (KeyError, AttributeError, TypeError, ValueError):
            pass

        history = ticker.history(period='5d', interval='1m')
        if history.empty:
            history = ticker.history(period='5d')
        if history.empty or 'Close' not in history:
            raise PriceFetchError(f'No current price available for {symbol}')
        return _to_decimal(history['Close'].iloc[-1])

    def _intervals_for(self, when: datetime.datetime) -> list[str]:
        age = timezone.now() - when
        if age <= datetime.timedelta(days=7):
            return ['1m', '5m', '1h', '1d']
        if age <= datetime.timedelta(days=60):
            return ['15m', '1h', '1d']
        if age <= datetime.timedelta(days=730):
            return ['1h', '1d']
        return ['1d']

    def _fetch_symbol_at(self, symbol: str, when: datetime.datetime) -> Decimal:
        last_error = None
        for interval in self._intervals_for(when):
            try:
                return self._fetch_symbol_interval(symbol, when, interval)
            except PriceFetchError as exc:
                last_error = exc
        raise last_error or PriceFetchError(
            f'No price available for {symbol} at {when.isoformat()}'
        )

    def _fetch_symbol_interval(
        self,
        symbol: str,
        when: datetime.datetime,
        interval: str,
    ) -> Decimal:
        lookback = INTERVAL_LOOKBACK[interval]
        start = when - lookback
        end = when + datetime.timedelta(minutes=1)
        try:
            history = yf.Ticker(symbol).history(
                start=start,
                end=end,
                interval=interval,
                auto_adjust=True,
            )
        except Exception as exc:
            raise PriceFetchError(f'Yahoo Finance request failed for {symbol}') from exc

        if history.empty or 'Close' not in history:
            raise PriceFetchError(f'No {interval} bars for {symbol} at {when.isoformat()}')

        target_utc = _to_utc(when)
        close = None
        for timestamp, row in history.iterrows():
            bar_time = _bar_utc(timestamp)
            value = row['Close']
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            if bar_time <= target_utc:
                close = value

        if close is None:
            raise PriceFetchError(
                f'No {interval} close on or before {when.isoformat()} for {symbol}'
            )
        return _to_decimal(close)


class PriceService:
    def __init__(self, fetcher: YFinanceFetcher | None = None):
        self.fetcher = fetcher or YFinanceFetcher()

    def get_historical_price(self, asset_code: str, when: datetime.datetime) -> Decimal:
        asset = _get_asset(asset_code)
        priced_at = _cache_timestamp(when)
        cached = HistoricalPrice.objects.filter(asset=asset, priced_at=priced_at).first()
        if cached is not None:
            return cached.price_try

        price = self.fetcher.fetch_price(asset_code, priced_at)
        HistoricalPrice.objects.create(asset=asset, priced_at=priced_at, price_try=price)
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
        transaction_date: datetime.datetime,
    ) -> Transaction:
        asset = _get_asset(asset_code)
        transaction_date = _ensure_aware(transaction_date)
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
