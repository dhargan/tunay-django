from __future__ import annotations

import datetime
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
from django.conf import settings
from django.utils import timezone
from evds import evdsAPI

from tunay.portfolio.models import (
    AssetType,
    HistoricalPrice,
    Transaction,
    TransactionType,
)

USD_TRY_SERIES = 'TP.DK.USD.A.YTL'
GOLD_GRAM_SERIES = 'TP.MK.KUL.YTL'
GOLD_ONS_USD_SERIES = 'TP.ALTINPIYASA.KAP03'
TROY_OUNCE_GRAMS = Decimal('31.1034768')
HISTORY_LOOKBACK_DAYS = 30
EVDS_CHUNK_DAYS = 100
PRICE_QUANTUM = Decimal('0.0001')
MONEY_QUANTUM = Decimal('0.01')


class PriceFetchError(Exception):
    """Raised when a TCMB EVDS price cannot be resolved."""


class UnknownAssetError(ValueError):
    """Raised when an asset code is not a known AssetType."""


class InsufficientHoldingsError(ValueError):
    """Raised when a SELL exceeds remaining quantity of an asset."""


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


def _is_sell(transaction: Transaction) -> bool:
    return transaction.transaction_type == TransactionType.SELL


def _apply_lot(
    quantity: Decimal,
    cost: Decimal,
    transaction: Transaction,
    *,
    strict: bool = True,
) -> tuple[Decimal, Decimal, Decimal | None]:
    amount = _to_decimal(transaction.amount)
    cash = _to_decimal(transaction.total_paid_try, MONEY_QUANTUM)
    if _is_sell(transaction):
        if amount > quantity:
            if strict:
                raise InsufficientHoldingsError(
                    f'Yetersiz bakiye: {transaction.asset} için {amount} satılamaz '
                    f'(mevcut {quantity}).'
                )
            amount = quantity
        if quantity <= 0 or amount <= 0:
            return quantity, cost, Decimal('0.00')
        average_cost = cost / quantity
        sale_price = cash / amount if amount else Decimal('0')
        realized = _to_decimal((sale_price - average_cost) * amount, MONEY_QUANTUM)
        quantity -= amount
        cost -= average_cost * amount
        if quantity <= 0:
            quantity = Decimal('0')
            cost = Decimal('0')
        else:
            quantity = _to_decimal(quantity)
            cost = _to_decimal(cost, MONEY_QUANTUM)
        return quantity, cost, realized

    quantity = _to_decimal(quantity + amount)
    cost = _to_decimal(cost + cash, MONEY_QUANTUM)
    return quantity, cost, None


def _replay_lots(
    transactions: list[Transaction],
    *,
    strict: bool = True,
) -> tuple[Decimal, Decimal, Decimal]:
    quantity = Decimal('0')
    cost = Decimal('0')
    realized_total = Decimal('0')
    for transaction in transactions:
        quantity, cost, realized = _apply_lot(
            quantity,
            cost,
            transaction,
            strict=strict,
        )
        if realized is not None:
            realized_total += realized
    return quantity, cost, _to_decimal(realized_total, MONEY_QUANTUM)


def _format_evds_date(value: datetime.date) -> str:
    return value.strftime('%d-%m-%Y')


def _parse_evds_date(value: object) -> datetime.date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    if not text or text in {'-', 'None', 'nan'}:
        return None
    for fmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, dayfirst=True, errors='coerce')
    if pd.isna(parsed):
        return None
    return parsed.date()


def _to_rate(value: object) -> Decimal | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace(',', '.')
    if not text or text in {'-', 'None', 'nan'}:
        return None
    try:
        return _to_decimal(text)
    except Exception:
        return None


class EvdsFetcher:
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key
        self._client = None

    @property
    def client(self):
        if self._client is None:
            key = self._api_key or getattr(settings, 'TCMB_EVDS_API_KEY', None)
            if not key:
                raise PriceFetchError('TCMB_EVDS_API_KEY is not configured')
            self._client = evdsAPI(key)
        return self._client

    def get_rate(
        self,
        asset_code: str,
        date: datetime.date | None = None,
    ) -> Decimal:
        return self.fetch_price(asset_code, date)

    def fetch_price(
        self,
        asset_code: str,
        date: datetime.date | None = None,
    ) -> Decimal:
        _require_asset_code(asset_code)
        as_of = timezone.localdate() if date is None else _as_date(date)
        observations = self._series_observations(asset_code, as_of)
        latest = self._latest_on_or_before(observations, as_of)
        if latest is None:
            raise PriceFetchError(
                f'No TCMB EVDS rate available for {asset_code} on or before {as_of}'
            )
        return latest[1]

    def fetch_live_quote(self, asset_code: str) -> dict[str, Decimal | str]:
        _require_asset_code(asset_code)
        as_of = timezone.localdate()
        observations = self._series_observations(asset_code, as_of)
        latest = self._latest_on_or_before(observations, as_of)
        if latest is None:
            raise PriceFetchError(f'No TCMB EVDS live rate available for {asset_code}')
        previous = self._latest_on_or_before(observations, latest[0] - datetime.timedelta(days=1))
        previous_close = previous[1] if previous is not None else latest[1]
        return _quote_from_prices(latest[1], previous_close)

    def fetch_rate_book(
        self,
        start: datetime.date,
        end: datetime.date,
    ) -> dict[str, list[tuple[datetime.date, Decimal]]]:
        start = _as_date(start) - datetime.timedelta(days=HISTORY_LOOKBACK_DAYS)
        end = _as_date(end)
        usd = self._fetch_series(USD_TRY_SERIES, start, end, frequency=2)
        gold = self._gold_from_ons_and_usd(start, end, usd_rows=dict(usd))
        if not gold:
            gold = self._fetch_series(GOLD_GRAM_SERIES, start, end)
        return {
            AssetType.USD: usd,
            AssetType.GA: gold,
        }

    def _series_observations(
        self,
        asset_code: str,
        as_of: datetime.date,
    ) -> list[tuple[datetime.date, Decimal]]:
        start = as_of - datetime.timedelta(days=HISTORY_LOOKBACK_DAYS)
        if asset_code == AssetType.USD:
            return self._fetch_series(USD_TRY_SERIES, start, as_of, frequency=2)
        gold_observations = self._gold_from_ons_and_usd(start, as_of)
        if gold_observations:
            return gold_observations
        return self._fetch_series(GOLD_GRAM_SERIES, start, as_of)

    def _gold_from_ons_and_usd(
        self,
        start: datetime.date,
        as_of: datetime.date,
        usd_rows: dict[datetime.date, Decimal] | None = None,
    ) -> list[tuple[datetime.date, Decimal]]:
        if usd_rows is None:
            usd_rows = dict(self._fetch_series(USD_TRY_SERIES, start, as_of, frequency=2))
        ons_rows = dict(
            self._fetch_series(GOLD_ONS_USD_SERIES, start, as_of, frequency=2)
        )
        if not usd_rows or not ons_rows:
            return []
        combined = []
        for day, ounce_usd in sorted(ons_rows.items()):
            usdtry = self._latest_on_or_before(list(usd_rows.items()), day)
            if usdtry is None:
                continue
            combined.append(
                (day, _to_decimal((ounce_usd / TROY_OUNCE_GRAMS) * usdtry[1]))
            )
        return combined

    def _fetch_series(
        self,
        series_code: str,
        start: datetime.date,
        end: datetime.date,
        frequency: int | str = '',
    ) -> list[tuple[datetime.date, Decimal]]:
        if (end - start).days > EVDS_CHUNK_DAYS:
            merged: dict[datetime.date, Decimal] = {}
            cursor = start
            while cursor <= end:
                chunk_end = min(cursor + datetime.timedelta(days=EVDS_CHUNK_DAYS), end)
                for day, rate in self._fetch_series_window(
                    series_code,
                    cursor,
                    chunk_end,
                    frequency,
                ):
                    merged[day] = rate
                cursor = chunk_end + datetime.timedelta(days=1)
            return sorted(merged.items())
        return self._fetch_series_window(series_code, start, end, frequency)

    def _fetch_series_window(
        self,
        series_code: str,
        start: datetime.date,
        end: datetime.date,
        frequency: int | str = '',
    ) -> list[tuple[datetime.date, Decimal]]:
        try:
            kwargs = {
                'startdate': _format_evds_date(start),
                'enddate': _format_evds_date(end),
            }
            if frequency != '':
                kwargs['frequency'] = frequency
            frame = self.client.get_data([series_code], **kwargs)
        except Exception:
            return []

        if frame is None or getattr(frame, 'empty', True):
            return []

        date_column = self._date_column(frame)
        value_column = self._value_column(frame, series_code)
        observations = []
        for _, row in frame.iterrows():
            day = _parse_evds_date(row[date_column])
            rate = _to_rate(row[value_column])
            if day is None or rate is None:
                continue
            observations.append((day, rate))
        observations.sort(key=lambda item: item[0])
        return observations

    @staticmethod
    def _date_column(frame: pd.DataFrame) -> str:
        for name in ('Tarih', 'TARIH', 'Date', 'date'):
            if name in frame.columns:
                return name
        return frame.columns[0]

    @staticmethod
    def _value_column(frame: pd.DataFrame, series_code: str) -> str:
        preferred = series_code.replace('.', '_')
        if preferred in frame.columns:
            return preferred
        skipped = {'Tarih', 'TARIH', 'Date', 'date', 'UNIXTIME', 'YEARWEEK'}
        for name in frame.columns:
            if name not in skipped:
                return name
        raise PriceFetchError(f'No value column in EVDS response for {series_code}')

    @staticmethod
    def _latest_on_or_before(
        observations: list[tuple[datetime.date, Decimal]],
        as_of: datetime.date,
    ) -> tuple[datetime.date, Decimal] | None:
        latest = None
        for day, rate in observations:
            if day <= as_of and (latest is None or day > latest[0]):
                latest = (day, rate)
        return latest


class PriceService:
    def __init__(self, fetcher: EvdsFetcher | None = None):
        self.fetcher = fetcher or EvdsFetcher()

    def get_rate(
        self,
        asset_code: str,
        date: datetime.date | None = None,
    ) -> Decimal:
        if date is None:
            return self.get_current_price(asset_code)
        return self.get_historical_price(asset_code, date)

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
        """Fetch the latest TCMB rate; never reads or writes HistoricalPrice."""
        return self.fetcher.fetch_price(_require_asset_code(asset_code))

    def get_live_quote(self, asset_code: str) -> dict[str, Decimal | str]:
        """Latest TCMB rate plus change versus previous business day. No cache."""
        return self.fetcher.fetch_live_quote(_require_asset_code(asset_code))

    def get_rate_book(
        self,
        start: datetime.date,
        end: datetime.date,
    ) -> dict[str, list[tuple[datetime.date, Decimal]]]:
        """Bulk TCMB rates for [start, end]; not written to HistoricalPrice."""
        return self.fetcher.fetch_rate_book(start, end)


class TransactionService:
    def __init__(self, price_service: PriceService | None = None):
        self.price_service = price_service or PriceService()

    def _spread_fee(
        self,
        asset_code: str,
        amount: Decimal,
        total_paid_try: Decimal,
        transaction_date: datetime.date,
        transaction_type: str,
    ) -> Decimal:
        market_price = self.price_service.get_historical_price(asset_code, transaction_date)
        market_value = amount * market_price
        if transaction_type == TransactionType.SELL:
            return _to_decimal(
                max(Decimal('0'), market_value - total_paid_try),
                MONEY_QUANTUM,
            )
        return _to_decimal(
            max(Decimal('0'), total_paid_try - market_value),
            MONEY_QUANTUM,
        )

    def _realized_pnl_for(
        self,
        draft: Transaction,
        exclude_pk: int | None = None,
    ) -> Decimal | None:
        existing = list(
            Transaction.objects.exclude(pk=exclude_pk or 0).order_by(
                'transaction_date',
                'id',
            )
        )
        combined = existing + [draft]
        combined.sort(key=lambda tx: (tx.transaction_date, tx.pk or 10**18))
        realized = None
        by_asset: dict[str, list[Transaction]] = {}
        for transaction in combined:
            by_asset.setdefault(transaction.asset, []).append(transaction)
        for rows in by_asset.values():
            quantity = Decimal('0')
            cost = Decimal('0')
            for transaction in rows:
                quantity, cost, lot_realized = _apply_lot(
                    quantity,
                    cost,
                    transaction,
                    strict=True,
                )
                if transaction is draft:
                    realized = lot_realized
        return realized

    def create_transaction(
        self,
        asset_code: str,
        amount: Decimal,
        total_paid_try: Decimal,
        transaction_date: datetime.date,
        transaction_type: str = TransactionType.BUY,
    ) -> Transaction:
        asset_code = _require_asset_code(asset_code)
        transaction_date = _as_date(transaction_date)
        amount = _to_decimal(amount)
        total_paid_try = _to_decimal(total_paid_try, MONEY_QUANTUM)
        transaction_type = transaction_type or TransactionType.BUY
        draft = Transaction(
            asset=asset_code,
            transaction_type=transaction_type,
            amount=amount,
            total_paid_try=total_paid_try,
            transaction_date=transaction_date,
        )
        realized_pnl = self._realized_pnl_for(draft)
        created = Transaction.objects.create(
            asset=asset_code,
            transaction_type=transaction_type,
            amount=amount,
            total_paid_try=total_paid_try,
            spread_fee_try=self._spread_fee(
                asset_code,
                amount,
                total_paid_try,
                transaction_date,
                transaction_type,
            ),
            realized_pnl=realized_pnl,
            transaction_date=transaction_date,
        )
        return created

    def update_transaction(
        self,
        transaction: Transaction,
        asset_code: str,
        amount: Decimal,
        total_paid_try: Decimal,
        transaction_date: datetime.date,
        transaction_type: str | None = None,
    ) -> Transaction:
        asset_code = _require_asset_code(asset_code)
        transaction_date = _as_date(transaction_date)
        amount = _to_decimal(amount)
        total_paid_try = _to_decimal(total_paid_try, MONEY_QUANTUM)
        transaction_type = transaction_type or transaction.transaction_type
        draft = Transaction(
            pk=transaction.pk,
            asset=asset_code,
            transaction_type=transaction_type,
            amount=amount,
            total_paid_try=total_paid_try,
            transaction_date=transaction_date,
        )
        realized_pnl = self._realized_pnl_for(draft, exclude_pk=transaction.pk)
        transaction.asset = asset_code
        transaction.transaction_type = transaction_type
        transaction.amount = amount
        transaction.total_paid_try = total_paid_try
        transaction.transaction_date = transaction_date
        transaction.realized_pnl = realized_pnl
        transaction.spread_fee_try = self._spread_fee(
            asset_code,
            amount,
            total_paid_try,
            transaction_date,
            transaction_type,
        )
        transaction.save()
        return transaction

    def delete_transaction(self, transaction: Transaction) -> None:
        transaction.delete()


class PortfolioAnalyticsService:
    def __init__(self, price_service: PriceService | None = None):
        self.price_service = price_service or PriceService()

    def calculate_transaction_pnl(self, transaction: Transaction) -> dict[str, Decimal | None]:
        if _is_sell(transaction):
            realized = transaction.realized_pnl
            if realized is None:
                realized = Decimal('0')
            realized = _to_decimal(realized, MONEY_QUANTUM)
            return {
                'current_value': Decimal('0.00'),
                'pnl_try': realized,
                'pnl_percentage': self._pnl_percentage(
                    realized,
                    transaction.total_paid_try,
                ),
                'spread_fee_try': transaction.spread_fee_try,
            }
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
        transactions = list(Transaction.objects.order_by('transaction_date', 'id'))
        today = timezone.localdate()
        by_asset: dict[str, list[Transaction]] = {}
        for transaction in transactions:
            by_asset.setdefault(transaction.asset, []).append(transaction)

        quotes: dict[str, dict[str, Decimal | str]] = {}
        remaining_cost = Decimal('0')
        current_total_value = Decimal('0')
        realized_total = Decimal('0')
        buy_cash = Decimal('0')
        today_change_try = Decimal('0')
        start_of_day_value = Decimal('0')
        asset_breakdown = []

        for asset_code, rows in by_asset.items():
            if asset_code not in quotes:
                quotes[asset_code] = self.price_service.get_live_quote(asset_code)
            price = quotes[asset_code]['price']
            previous_close = quotes[asset_code]['previous_close']
            prior = [row for row in rows if row.transaction_date < today]
            qty_open, _, _ = _replay_lots(prior, strict=False)
            quantity, cost, realized = _replay_lots(rows, strict=False)
            market_value = quantity * price
            unrealized = market_value - cost
            remaining_cost += cost
            realized_total += realized
            current_total_value += market_value
            start_of_day_value += qty_open * previous_close
            asset_breakdown.append({
                'code': asset_code,
                'name': AssetType(asset_code).label,
                'total_amount': _to_decimal(quantity),
                'total_cost_try': _to_decimal(cost, MONEY_QUANTUM),
                'current_market_value': _to_decimal(market_value, MONEY_QUANTUM),
                'pnl_try': _to_decimal(unrealized + realized, MONEY_QUANTUM),
                'pnl_percentage': self._pnl_percentage(unrealized, cost),
            })
            today_buys = Decimal('0')
            today_sells = Decimal('0')
            for row in rows:
                if not _is_sell(row):
                    buy_cash += row.total_paid_try
                if row.transaction_date != today:
                    continue
                if _is_sell(row):
                    today_sells += row.total_paid_try
                else:
                    today_buys += row.total_paid_try
            today_change_try += (
                quantity * price
                - qty_open * previous_close
                + today_sells
                - today_buys
            )

        remaining_cost = _to_decimal(remaining_cost, MONEY_QUANTUM)
        current_total_value = _to_decimal(current_total_value, MONEY_QUANTUM)
        realized_total = _to_decimal(realized_total, MONEY_QUANTUM)
        buy_cash = _to_decimal(buy_cash, MONEY_QUANTUM)
        unrealized = _to_decimal(current_total_value - remaining_cost, MONEY_QUANTUM)
        total_pnl_try = _to_decimal(unrealized + realized_total, MONEY_QUANTUM)
        today_change_try = _to_decimal(today_change_try, MONEY_QUANTUM)
        baseline = start_of_day_value if start_of_day_value else buy_cash
        return {
            'total_invested': remaining_cost,
            'current_total_value': current_total_value,
            'total_pnl_try': total_pnl_try,
            'total_pnl_percentage': self._pnl_percentage(total_pnl_try, buy_cash),
            'today_change_try': today_change_try,
            'today_change_percentage': self._pnl_percentage(today_change_try, baseline),
            'realized_pnl_try': realized_total,
            'asset_breakdown': asset_breakdown,
        }

    def generate_weekly_pnl(self) -> dict[str, list]:
        transactions = list(Transaction.objects.order_by('transaction_date', 'id'))
        empty = {'weeks': [], 'usd_pnl': [], 'ga_pnl': []}
        if not transactions:
            return empty

        today = timezone.localdate()
        start = transactions[0].transaction_date
        try:
            rate_book = self.price_service.get_rate_book(start, today)
        except PriceFetchError:
            return empty

        by_asset: dict[str, list[Transaction]] = {}
        for transaction in transactions:
            by_asset.setdefault(transaction.asset, []).append(transaction)

        weeks: list[str] = []
        usd_pnl: list[float] = []
        ga_pnl: list[float] = []
        for as_of in self._iso_week_ends(start, today):
            weeks.append(self._week_label(as_of))
            usd_pnl.append(
                float(self._asset_pnl_as_of(by_asset.get(AssetType.USD, []), rate_book.get(AssetType.USD, []), as_of))
            )
            ga_pnl.append(
                float(self._asset_pnl_as_of(by_asset.get(AssetType.GA, []), rate_book.get(AssetType.GA, []), as_of))
            )
        return {
            'weeks': weeks,
            'usd_pnl': usd_pnl,
            'ga_pnl': ga_pnl,
        }

    def _asset_pnl_as_of(
        self,
        rows: list[Transaction],
        observations: list[tuple[datetime.date, Decimal]],
        as_of: datetime.date,
    ) -> Decimal:
        eligible = [row for row in rows if row.transaction_date <= as_of]
        quantity, cost, realized = _replay_lots(eligible, strict=False)
        quoted = EvdsFetcher._latest_on_or_before(observations, as_of)
        price = quoted[1] if quoted is not None else Decimal('0')
        market_value = _to_decimal(quantity * price, MONEY_QUANTUM) if quantity else Decimal('0')
        return _to_decimal(market_value - cost + realized, MONEY_QUANTUM)

    @staticmethod
    def _iso_week_ends(start: datetime.date, end: datetime.date) -> list[datetime.date]:
        week_end = start + datetime.timedelta(days=6 - start.weekday())
        ends = []
        while True:
            ends.append(min(week_end, end))
            if week_end >= end:
                break
            week_end += datetime.timedelta(days=7)
        return ends

    @staticmethod
    def _week_label(week_end: datetime.date) -> str:
        return week_end.strftime('%d.%m.%Y')

    @staticmethod
    def _pnl_percentage(pnl_try: Decimal, invested: Decimal) -> Decimal:
        if invested == 0:
            return Decimal('0.00')
        return _to_decimal((pnl_try / invested) * Decimal('100'), MONEY_QUANTUM)
