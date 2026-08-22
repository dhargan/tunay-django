from __future__ import annotations

import calendar
import datetime
from decimal import Decimal, ROUND_HALF_UP

import yfinance as yf
from django.utils import timezone

from tunay.portfolio.models import (
    AssetType,
    HistoricalPrice,
    MonthlyPortfolioSnapshot,
    Transaction,
)

USDTRY_SYMBOL = 'USDTRY=X'
GOLD_FUTURES_SYMBOL = 'GC=F'
TROY_OUNCE_GRAMS = Decimal('31.1034768')
HISTORY_LOOKBACK_DAYS = 21
PRICE_QUANTUM = Decimal('0.0001')
MONEY_QUANTUM = Decimal('0.01')


class PriceFetchError(Exception):
    """Raised when a Yahoo Finance price cannot be resolved."""


class UnknownAssetError(ValueError):
    """Raised when an asset code is not a known AssetType."""


def _to_decimal(value: object, quantum: Decimal = PRICE_QUANTUM) -> Decimal:
    if isinstance(value, Decimal):
        number = value
    else:
        number = Decimal(str(value))
    return number.quantize(quantum, rounding=ROUND_HALF_UP)


def _require_asset_code(asset_code: str) -> str:
    if asset_code not in AssetType.values:
        raise UnknownAssetError(f'Unsupported asset code: {asset_code}')
    return asset_code


def _quote_from_prices(price: Decimal, previous_close: Decimal) -> dict[str, Decimal | str]:
    if previous_close == 0:
        change_pct = Decimal('0.00')
    else:
        change_pct = _to_decimal(
            ((price - previous_close) / previous_close) * Decimal('100'),
            MONEY_QUANTUM,
        )
    if change_pct > 0:
        trend = 'up'
    elif change_pct < 0:
        trend = 'down'
    else:
        trend = 'neutral'
    return {
        'price': price,
        'previous_close': previous_close,
        'change_pct': change_pct,
        'trend': trend,
    }


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
        if asset_code == AssetType.USD:
            return self._fetch_symbol_current(USDTRY_SYMBOL)
        gold_usd = self._fetch_symbol_current(GOLD_FUTURES_SYMBOL)
        usdtry = self._fetch_symbol_current(USDTRY_SYMBOL)
        return _to_decimal((gold_usd / TROY_OUNCE_GRAMS) * usdtry)

    def _historical_asset_price(self, asset_code: str, date: datetime.date) -> Decimal:
        if asset_code == AssetType.USD:
            return self._fetch_symbol_close(USDTRY_SYMBOL, date)
        gold_usd = self._fetch_symbol_close(GOLD_FUTURES_SYMBOL, date)
        usdtry = self._fetch_symbol_close(USDTRY_SYMBOL, date)
        return _to_decimal((gold_usd / TROY_OUNCE_GRAMS) * usdtry)

    def _fetch_symbol_snapshot(self, symbol: str) -> tuple[Decimal, Decimal]:
        try:
            return self._fetch_symbol_snapshot_unsafe(symbol)
        except PriceFetchError:
            raise
        except Exception as exc:
            raise PriceFetchError(f'Yahoo Finance request failed for {symbol}') from exc

    def _fetch_symbol_snapshot_unsafe(self, symbol: str) -> tuple[Decimal, Decimal]:
        ticker = yf.Ticker(symbol)
        current = None
        previous_close = None
        try:
            info = ticker.fast_info
            current = info.last_price
            previous_close = getattr(info, 'previous_close', None)
            if previous_close is None:
                previous_close = info.get('previousClose')
        except (KeyError, AttributeError, TypeError, ValueError):
            pass

        if current is None or previous_close is None:
            history = ticker.history(period='5d')
            if history.empty or 'Close' not in history:
                raise PriceFetchError(f'No current price available for {symbol}')
            current = history['Close'].iloc[-1]
            if previous_close is None:
                previous_close = (
                    history['Close'].iloc[-2]
                    if len(history) > 1
                    else history['Close'].iloc[-1]
                )
        return _to_decimal(current), _to_decimal(previous_close)

    def fetch_live_quote(self, asset_code: str) -> dict[str, Decimal | str]:
        _require_asset_code(asset_code)
        if asset_code == AssetType.USD:
            price, previous_close = self._fetch_symbol_snapshot(USDTRY_SYMBOL)
        else:
            gold_price, gold_prev = self._fetch_symbol_snapshot(GOLD_FUTURES_SYMBOL)
            usd_price, usd_prev = self._fetch_symbol_snapshot(USDTRY_SYMBOL)
            price = _to_decimal((gold_price / TROY_OUNCE_GRAMS) * usd_price)
            previous_close = _to_decimal((gold_prev / TROY_OUNCE_GRAMS) * usd_prev)
        return _quote_from_prices(price, previous_close)

    def _fetch_symbol_current(self, symbol: str) -> Decimal:
        try:
            return self._fetch_symbol_current_unsafe(symbol)
        except PriceFetchError:
            raise
        except Exception as exc:
            raise PriceFetchError(f'Yahoo Finance request failed for {symbol}') from exc

    def _fetch_symbol_current_unsafe(self, symbol: str) -> Decimal:
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
        try:
            return self._fetch_symbol_close_unsafe(symbol, date)
        except PriceFetchError:
            raise
        except Exception as exc:
            raise PriceFetchError(f'Yahoo Finance request failed for {symbol}') from exc

    def _fetch_symbol_close_unsafe(self, symbol: str, date: datetime.date) -> Decimal:
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
        asset_code = _require_asset_code(asset_code)
        date = _as_date(date)
        cached = HistoricalPrice.objects.filter(asset=asset_code, date=date).first()
        if cached is not None:
            return cached.price_try

        price = self.fetcher.fetch_price(asset_code, date)
        HistoricalPrice.objects.create(asset=asset_code, date=date, price_try=price)
        return price

    def get_current_price(self, asset_code: str) -> Decimal:
        """Fetch the live market price; never reads or writes HistoricalPrice."""
        return self.fetcher.fetch_price(_require_asset_code(asset_code))

    def get_live_quote(self, asset_code: str) -> dict[str, Decimal | str]:
        """Live price plus daily change versus previous close. No cache."""
        return self.fetcher.fetch_live_quote(_require_asset_code(asset_code))


class TransactionService:
    def __init__(self, price_service: PriceService | None = None):
        self.price_service = price_service or PriceService()

    def _spread_fee(
        self,
        asset_code: str,
        amount: Decimal,
        total_paid_try: Decimal,
        transaction_date: datetime.date,
    ) -> Decimal:
        market_price = self.price_service.get_historical_price(asset_code, transaction_date)
        market_value = amount * market_price
        return _to_decimal(
            max(Decimal('0'), total_paid_try - market_value),
            MONEY_QUANTUM,
        )

    def create_transaction(
        self,
        asset_code: str,
        amount: Decimal,
        total_paid_try: Decimal,
        transaction_date: datetime.date,
    ) -> Transaction:
        asset_code = _require_asset_code(asset_code)
        transaction_date = _as_date(transaction_date)
        amount = _to_decimal(amount)
        total_paid_try = _to_decimal(total_paid_try, MONEY_QUANTUM)
        created = Transaction.objects.create(
            asset=asset_code,
            amount=amount,
            total_paid_try=total_paid_try,
            spread_fee_try=self._spread_fee(
                asset_code,
                amount,
                total_paid_try,
                transaction_date,
            ),
            transaction_date=transaction_date,
        )
        self._refresh_monthly_snapshots()
        return created

    def update_transaction(
        self,
        transaction: Transaction,
        asset_code: str,
        amount: Decimal,
        total_paid_try: Decimal,
        transaction_date: datetime.date,
    ) -> Transaction:
        asset_code = _require_asset_code(asset_code)
        transaction_date = _as_date(transaction_date)
        amount = _to_decimal(amount)
        total_paid_try = _to_decimal(total_paid_try, MONEY_QUANTUM)
        transaction.asset = asset_code
        transaction.amount = amount
        transaction.total_paid_try = total_paid_try
        transaction.transaction_date = transaction_date
        transaction.spread_fee_try = self._spread_fee(
            asset_code,
            amount,
            total_paid_try,
            transaction_date,
        )
        transaction.save()
        self._refresh_monthly_snapshots()
        return transaction

    def delete_transaction(self, transaction: Transaction) -> None:
        transaction.delete()
        self._refresh_monthly_snapshots()

    def _refresh_monthly_snapshots(self) -> None:
        PortfolioAnalyticsService(price_service=self.price_service).recalculate_monthly_snapshots()


class PortfolioAnalyticsService:
    def __init__(self, price_service: PriceService | None = None):
        self.price_service = price_service or PriceService()

    def calculate_transaction_pnl(self, transaction: Transaction) -> dict[str, Decimal | None]:
        current_price = self.price_service.get_current_price(transaction.asset)
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
        transactions = list(Transaction.objects.all())
        today = timezone.localdate()
        total_invested = Decimal('0')
        current_total_value = Decimal('0')
        today_change_try = Decimal('0')
        start_of_day_value = Decimal('0')
        quotes: dict[str, dict[str, Decimal | str]] = {}

        for transaction in transactions:
            total_invested += transaction.total_paid_try
            code = transaction.asset
            if code not in quotes:
                quotes[code] = self.price_service.get_live_quote(code)
            price = quotes[code]['price']
            previous_close = quotes[code]['previous_close']
            current_value = transaction.amount * price
            current_total_value += current_value

            if transaction.transaction_date < today:
                start_of_day_value += transaction.amount * previous_close
                today_change_try += transaction.amount * (price - previous_close)
            elif transaction.transaction_date == today:
                today_change_try += current_value - transaction.total_paid_try

        total_invested = _to_decimal(total_invested, MONEY_QUANTUM)
        current_total_value = _to_decimal(current_total_value, MONEY_QUANTUM)
        total_pnl_try = _to_decimal(current_total_value - total_invested, MONEY_QUANTUM)
        today_change_try = _to_decimal(today_change_try, MONEY_QUANTUM)
        baseline = start_of_day_value if start_of_day_value else total_invested
        return {
            'total_invested': total_invested,
            'current_total_value': current_total_value,
            'total_pnl_try': total_pnl_try,
            'total_pnl_percentage': self._pnl_percentage(total_pnl_try, total_invested),
            'today_change_try': today_change_try,
            'today_change_percentage': self._pnl_percentage(today_change_try, baseline),
        }

    def get_monthly_pnl_breakdown(self) -> dict[str, list]:
        snapshots = MonthlyPortfolioSnapshot.objects.order_by('year', 'month', 'asset_code')
        by_month: dict[tuple[int, int], dict[str, float]] = {}
        for snapshot in snapshots:
            key = (snapshot.year, snapshot.month)
            if key not in by_month:
                by_month[key] = {'USD': 0.0, 'GA': 0.0}
            by_month[key][snapshot.asset_code] = float(snapshot.pnl_try)

        months = []
        usd_pnl = []
        ga_pnl = []
        for year, month in by_month:
            months.append(self._month_label(datetime.date(year, month, 1)))
            usd_pnl.append(by_month[(year, month)]['USD'])
            ga_pnl.append(by_month[(year, month)]['GA'])
        return {
            'months': months,
            'usd_pnl': usd_pnl,
            'ga_pnl': ga_pnl,
        }

    def recalculate_monthly_snapshots(self) -> None:
        MonthlyPortfolioSnapshot.objects.all().delete()
        transactions = list(Transaction.objects.order_by('transaction_date'))
        if not transactions:
            return

        today = timezone.localdate()
        month_starts = self._month_range(
            transactions[0].transaction_date.replace(day=1),
            today.replace(day=1),
        )
        snapshots = []
        for month_start in month_starts:
            as_of = min(self._month_end(month_start), today)
            for asset_code in AssetType.values:
                total_amount = Decimal('0')
                total_cost_try = Decimal('0')
                for transaction in transactions:
                    if transaction.asset != asset_code:
                        continue
                    if transaction.transaction_date > as_of:
                        continue
                    total_amount += transaction.amount
                    total_cost_try += transaction.total_paid_try

                market_value_try = Decimal('0')
                if total_amount:
                    try:
                        price = self.price_service.get_historical_price(asset_code, as_of)
                    except PriceFetchError:
                        price = Decimal('0')
                    market_value_try = _to_decimal(total_amount * price, MONEY_QUANTUM)
                total_cost_try = _to_decimal(total_cost_try, MONEY_QUANTUM)
                snapshots.append(
                    MonthlyPortfolioSnapshot(
                        year=month_start.year,
                        month=month_start.month,
                        asset_code=asset_code,
                        total_amount=_to_decimal(total_amount),
                        total_cost_try=total_cost_try,
                        market_value_try=market_value_try,
                        pnl_try=_to_decimal(market_value_try - total_cost_try, MONEY_QUANTUM),
                    )
                )
        MonthlyPortfolioSnapshot.objects.bulk_create(snapshots)

    @staticmethod
    def _month_end(month_start: datetime.date) -> datetime.date:
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        return month_start.replace(day=last_day)

    @staticmethod
    def _month_range(start: datetime.date, end: datetime.date) -> list[datetime.date]:
        months = []
        current = start
        while current <= end:
            months.append(current)
            if current.month == 12:
                current = datetime.date(current.year + 1, 1, 1)
            else:
                current = datetime.date(current.year, current.month + 1, 1)
        return months

    @staticmethod
    def _month_label(month_start: datetime.date) -> str:
        names = (
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
        )
        return f'{names[month_start.month - 1]} {month_start.year}'

    @staticmethod
    def _pnl_percentage(pnl_try: Decimal, invested: Decimal) -> Decimal:
        if invested == 0:
            return Decimal('0.00')
        return _to_decimal((pnl_try / invested) * Decimal('100'), MONEY_QUANTUM)
