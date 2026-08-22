from django.db import models


class Asset(models.Model):
    ASSET_CHOICES = [
        ('USD', 'US Dollar'),
        ('GA', 'Gram Gold'),
    ]

    code = models.CharField(max_length=10, choices=ASSET_CHOICES, unique=True)
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class HistoricalPrice(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    priced_at = models.DateTimeField()
    price_try = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        unique_together = ['asset', 'priced_at']

    def __str__(self):
        return f'{self.asset_id} {self.priced_at}'


class Transaction(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=4)
    total_paid_try = models.DecimalField(max_digits=12, decimal_places=2)
    spread_fee_try = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    transaction_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def effective_unit_cost(self):
        return self.total_paid_try / self.amount

    def __str__(self):
        return f'{self.asset_id} {self.transaction_date}'
