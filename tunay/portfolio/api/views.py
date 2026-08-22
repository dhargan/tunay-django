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
    http_method_names = ['get', 'post', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return TransactionCreateSerializer
        return TransactionDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transaction = TransactionService().create_transaction(
                **serializer.validated_data
            )
        except UnknownAssetError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PriceFetchError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            TransactionDetailSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )
