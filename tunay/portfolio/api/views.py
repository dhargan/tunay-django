import logging

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from tunay.portfolio.api.serializers import (
    TransactionCreateSerializer,
    TransactionDetailSerializer,
)
from tunay.portfolio.models import AssetType, Transaction
from tunay.portfolio.services import (
    InsufficientHoldingsError,
    PriceFetchError,
    PortfolioAnalyticsService,
    TransactionService,
    UnknownAssetError,
)

logger = logging.getLogger(__name__)

EMPTY_KPI = {
    'total_invested': 0,
    'current_total_value': 0,
    'total_pnl_try': 0,
    'total_pnl_percentage': 0,
    'today_change_try': 0,
    'today_change_percentage': 0,
    'realized_pnl_try': 0,
    'asset_breakdown': [],
}


class DashboardAPIView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        analytics = PortfolioAnalyticsService()
        metrics = dict(EMPTY_KPI)
        metrics['live_rates'] = {}
        metrics['monthly_pnl'] = {'months': [], 'usd_pnl': [], 'ga_pnl': []}

        try:
            metrics.update(analytics.calculate_cumulative_pnl())
        except Exception:
            logger.exception('Dashboard KPI calculation failed')

        try:
            metrics['live_rates'] = {
                'USD': analytics.price_service.get_live_quote('USD'),
                'GA': analytics.price_service.get_live_quote('GA'),
            }
        except Exception:
            logger.exception('Dashboard live rates failed')

        try:
            metrics['monthly_pnl'] = analytics.get_monthly_pnl_breakdown()
        except Exception:
            logger.exception('Dashboard monthly PnL failed')

        return Response(metrics)


class AssetListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        return Response([
            {'code': code, 'name': label}
            for code, label in AssetType.choices
        ])


class TransactionViewSet(ModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    queryset = Transaction.objects.all().order_by('-transaction_date', '-id')
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

    def get_serializer_class(self):
        if self.action in {'create', 'update', 'partial_update'}:
            return TransactionCreateSerializer
        return TransactionDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._persist(serializer.validated_data, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        return self._update_from_request(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_from_request(request, partial=True)

    def _update_from_request(self, request, partial: bool):
        transaction = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = {
            'asset_code': serializer.validated_data.get('asset_code', transaction.asset),
            'transaction_type': serializer.validated_data.get(
                'transaction_type',
                transaction.transaction_type,
            ),
            'amount': serializer.validated_data.get('amount', transaction.amount),
            'total_paid_try': serializer.validated_data.get(
                'total_paid_try',
                transaction.total_paid_try,
            ),
            'transaction_date': serializer.validated_data.get(
                'transaction_date',
                transaction.transaction_date,
            ),
        }
        return self._persist(data, status.HTTP_200_OK, transaction=transaction)

    def _persist(self, data, success_status, transaction=None):
        service = TransactionService()
        try:
            if transaction is None:
                saved = service.create_transaction(**data)
            else:
                saved = service.update_transaction(transaction, **data)
        except UnknownAssetError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientHoldingsError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PriceFetchError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(TransactionDetailSerializer(saved).data, status=success_status)

    def destroy(self, request, *args, **kwargs):
        transaction = self.get_object()
        TransactionService().delete_transaction(transaction)
        return Response(status=status.HTTP_204_NO_CONTENT)
