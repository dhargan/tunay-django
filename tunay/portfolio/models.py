from django.db import models


class AssetType(models.TextChoices):
    USD = 'USD', 'ABD Doları'
    GA = 'GA', 'Gram altın'


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
    amount = models.DecimalField(max_digits=12, decimal_places=4)
    total_paid_try = models.DecimalField(max_digits=12, decimal_places=2)
    spread_fee_try = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    transaction_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def effective_unit_cost(self):
        return self.total_paid_try / self.amount

    def __str__(self):
        return f'{self.asset} {self.transaction_date}'
