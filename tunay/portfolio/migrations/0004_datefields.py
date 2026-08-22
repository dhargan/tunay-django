from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portfolio', '0003_historical_price_datetime'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='transaction_date',
            field=models.DateField(),
        ),
        migrations.AlterUniqueTogether(
            name='historicalprice',
            unique_together=set(),
        ),
        migrations.RenameField(
            model_name='historicalprice',
            old_name='priced_at',
            new_name='date',
        ),
        migrations.AlterField(
            model_name='historicalprice',
            name='date',
            field=models.DateField(),
        ),
        migrations.AlterUniqueTogether(
            name='historicalprice',
            unique_together={('asset', 'date')},
        ),
    ]
