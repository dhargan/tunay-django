from django.contrib import admin

from tunay.geoplate.models import City


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('plate_code', 'name')
    search_fields = ('name', 'plate_code')
    ordering = ('plate_code',)
