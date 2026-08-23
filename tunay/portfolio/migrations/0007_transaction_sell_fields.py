from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0006_monthly_portfolio_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='transaction_type',
            field=models.CharField(
                choices=[('BUY', 'Alış'), ('SELL', 'Satış')],
                default='BUY',
                max_length=4,
            ),
        ),
        migrations.AddField(
            model_name='transaction',
            name='realized_pnl',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
            ),
        ),
    ]
