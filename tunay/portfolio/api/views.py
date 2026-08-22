from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from tunay.portfolio.api.serializers import (
    TransactionCreateSerializer,
    TransactionDetailSerializer,
)
from tunay.portfolio.models import AssetType, Transaction
from tunay.portfolio.services import (
    PriceFetchError,
    PortfolioAnalyticsService,
    TransactionService,
    UnknownAssetError,
)


class DashboardAPIView(APIView):
    def get(self, request):
        metrics = PortfolioAnalyticsService().calculate_cumulative_pnl()
        return Response(metrics)


class AssetListView(APIView):
    def get(self, request):
        return Response([
            {'code': code, 'name': label}
            for code, label in AssetType.choices
        ])


class TransactionViewSet(ModelViewSet):
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
        except PriceFetchError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(TransactionDetailSerializer(saved).data, status=success_status)
