from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tunay.portfolio.api.views import AssetListView, DashboardAPIView, TransactionViewSet

router = DefaultRouter()
router.register(r'transactions', TransactionViewSet, basename='transaction')

urlpatterns = [
    path('dashboard/', DashboardAPIView.as_view(), name='portfolio-dashboard'),
    path('assets/', AssetListView.as_view(), name='portfolio-assets'),
    path('', include(router.urls)),
]
