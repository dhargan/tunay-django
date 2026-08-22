from rest_framework import serializers

from tunay.portfolio.models import Asset, Transaction
from tunay.portfolio.services import PortfolioAnalyticsService


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ['id', 'code', 'name']


class TransactionCreateSerializer(serializers.Serializer):
    asset_code = serializers.CharField(max_length=10)
    amount = serializers.DecimalField(max_digits=12, decimal_places=4)
    total_paid_try = serializers.DecimalField(max_digits=12, decimal_places=2)
    transaction_date = serializers.DateField()

    def validate_asset_code(self, value):
        valid_codes = {code for code, _ in Asset.ASSET_CHOICES}
        if value not in valid_codes:
            raise serializers.ValidationError(f'Unsupported asset code: {value}')
        if not Asset.objects.filter(code=value).exists():
            raise serializers.ValidationError(f'Asset {value} is not registered')
        return value


class TransactionDetailSerializer(serializers.ModelSerializer):
    asset = AssetSerializer(read_only=True)
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
            'amount',
            'total_paid_try',
            'spread_fee_try',
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

    def _pnl(self, transaction: Transaction) -> dict:
        if transaction.pk not in self._pnl_cache:
            self._pnl_cache[transaction.pk] = self._analytics.calculate_transaction_pnl(
                transaction
            )
        return self._pnl_cache[transaction.pk]

    def get_current_value(self, obj: Transaction):
        return self._pnl(obj)['current_value']

    def get_pnl_try(self, obj: Transaction):
        return self._pnl(obj)['pnl_try']

    def get_pnl_percentage(self, obj: Transaction):
        return self._pnl(obj)['pnl_percentage']
