from django.db import models


class AssetType(models.TextChoices):
    USD = 'USD', 'ABD Doları'
    GA = 'GA', 'Gram altın'


class TransactionType(models.TextChoices):
    BUY = 'BUY', 'Alış'
    SELL = 'SELL', 'Satış'


class HistoricalPrice(models.Model):
    asset = models.CharField(max_length=10, choices=AssetType.choices)
    date = models.DateField()
    price_try = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        unique_together = ['asset', 'date']

    def __str__(self):
        return f'{self.asset} {self.date}'


class Transaction(models.Model):
    asset = models.CharField(max_length=10, choices=AssetType.choices)
    transaction_type = models.CharField(
        max_length=4,
        choices=TransactionType.choices,
        default=TransactionType.BUY,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=4)
    total_paid_try = models.DecimalField(max_digits=12, decimal_places=2)
    spread_fee_try = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    realized_pnl = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    transaction_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_sell(self):
        return self.transaction_type == TransactionType.SELL

    @property
    def effective_unit_cost(self):
        if not self.amount:
            return None
        return self.total_paid_try / self.amount

    def __str__(self):
        return f'{self.get_transaction_type_display()} {self.asset} {self.transaction_date}'


class MonthlyPortfolioSnapshot(models.Model):
    year = models.IntegerField()
    month = models.IntegerField()
    asset_code = models.CharField(max_length=10, choices=AssetType.choices)
    total_amount = models.DecimalField(max_digits=12, decimal_places=4)
    total_cost_try = models.DecimalField(max_digits=12, decimal_places=2)
    market_value_try = models.DecimalField(max_digits=12, decimal_places=2)
    pnl_try = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ('year', 'month', 'asset_code')

    def __str__(self):
        return f'{self.asset_code} {self.year}-{self.month:02d}'
