from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def success_view(request):
    """
    Basit bir başarı mesajı döndüren endpoint.
    """
    return Response({"status": "success", "message": "İşlem başarılı!"}) 