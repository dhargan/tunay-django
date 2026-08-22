from django.urls import include, path

from tunay.portfolio.views import DashboardView

app_name = 'portfolio'

urlpatterns = [
    path('', DashboardView.as_view(), name='index'),
    path('api/', include('tunay.portfolio.api.urls')),
]
