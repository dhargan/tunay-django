from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from tunay.portfolio.api.serializers import (
    AssetSerializer,
    TransactionCreateSerializer,
    TransactionDetailSerializer,
)
from tunay.portfolio.models import Asset, Transaction
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


class AssetListView(ListAPIView):
    queryset = Asset.objects.all().order_by('code')
    serializer_class = AssetSerializer


class TransactionViewSet(ModelViewSet):
    queryset = Transaction.objects.select_related('asset').order_by(
        '-transaction_date',
        '-id',
    )
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

        transaction = Transaction.objects.select_related('asset').get(pk=transaction.pk)
        return Response(
            TransactionDetailSerializer(transaction).data,
            status=status.HTTP_201_CREATED,
        )
