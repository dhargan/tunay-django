from django.contrib import admin

from tunay.portfolio.models import (
    HistoricalPrice,
    MonthlyPortfolioSnapshot,
    Transaction,
)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'asset',
        'amount',
        'effective_unit_cost',
        'total_paid_try',
        'spread_fee_try',
        'transaction_date',
    )
    list_filter = ('asset', 'transaction_date')
    search_fields = ('asset',)
    readonly_fields = ('effective_unit_cost', 'created_at')
    date_hierarchy = 'transaction_date'
    ordering = ('-transaction_date', '-id')


@admin.register(HistoricalPrice)
class HistoricalPriceAdmin(admin.ModelAdmin):
    list_display = ('asset', 'price_try', 'date')
    list_filter = ('asset', 'date')
    search_fields = ('asset',)
    date_hierarchy = 'date'
    ordering = ('-date', 'asset')


@admin.register(MonthlyPortfolioSnapshot)
class MonthlyPortfolioSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        'year',
        'month',
        'asset_code',
        'total_amount',
        'total_cost_try',
        'market_value_try',
        'pnl_try',
    )
    list_filter = ('year', 'month', 'asset_code')
    ordering = ('-year', '-month', 'asset_code')
    readonly_fields = (
        'year',
        'month',
        'asset_code',
        'total_amount',
        'total_cost_try',
        'market_value_try',
        'pnl_try',
    )
