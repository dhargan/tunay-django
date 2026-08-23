from rest_framework import serializers

from tunay.portfolio.models import AssetType, HistoricalPrice, Transaction, TransactionType
from tunay.portfolio.services import PortfolioAnalyticsService, PriceFetchError


class TransactionCreateSerializer(serializers.Serializer):
    asset_code = serializers.ChoiceField(choices=AssetType.choices)
    transaction_type = serializers.ChoiceField(
        choices=TransactionType.choices,
        default=TransactionType.BUY,
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=4)
    total_paid_try = serializers.DecimalField(max_digits=12, decimal_places=2)
    transaction_date = serializers.DateField()


class TransactionDetailSerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()
    effective_unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=4,
        read_only=True,
    )
    current_value = serializers.SerializerMethodField()
    pnl_try = serializers.SerializerMethodField()
    pnl_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'id',
            'asset',
            'transaction_type',
            'amount',
            'total_paid_try',
            'spread_fee_try',
            'realized_pnl',
            'transaction_date',
            'created_at',
            'effective_unit_cost',
            'current_value',
            'pnl_try',
            'pnl_percentage',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._analytics = PortfolioAnalyticsService()
        self._pnl_cache = {}

    def get_asset(self, obj: Transaction) -> dict[str, str]:
        return {
            'code': obj.asset,
            'name': AssetType(obj.asset).label,
        }

    def _pnl(self, transaction: Transaction) -> dict:
        if transaction.pk not in self._pnl_cache:
            try:
                self._pnl_cache[transaction.pk] = self._analytics.calculate_transaction_pnl(
                    transaction
                )
            except PriceFetchError:
                if transaction.transaction_type == TransactionType.SELL:
                    realized = transaction.realized_pnl or 0
                    self._pnl_cache[transaction.pk] = {
                        'current_value': 0,
                        'pnl_try': realized,
                        'pnl_percentage': self._analytics._pnl_percentage(
                            realized,
                            transaction.total_paid_try,
                        ),
                        'spread_fee_try': transaction.spread_fee_try,
                    }
                    return self._pnl_cache[transaction.pk]
                last_price = (
                    HistoricalPrice.objects.filter(asset=transaction.asset)
                    .order_by('-date')
                    .values_list('price_try', flat=True)
                    .first()
                )
                if last_price is None:
                    raise
                current_value = transaction.amount * last_price
                pnl_try = current_value - transaction.total_paid_try
                self._pnl_cache[transaction.pk] = {
                    'current_value': current_value,
                    'pnl_try': pnl_try,
                    'pnl_percentage': self._analytics._pnl_percentage(
                        pnl_try,
                        transaction.total_paid_try,
                    ),
                    'spread_fee_try': transaction.spread_fee_try,
                }
        return self._pnl_cache[transaction.pk]

    def get_current_value(self, obj: Transaction):
        return self._pnl(obj)['current_value']

    def get_pnl_try(self, obj: Transaction):
        return self._pnl(obj)['pnl_try']

    def get_pnl_percentage(self, obj: Transaction):
        return self._pnl(obj)['pnl_percentage']
