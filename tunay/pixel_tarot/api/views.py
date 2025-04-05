from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def success_view(request):
    """
    A simple endpoint that returns a success message.
    """
    return Response({"status": "success", "message": "Operation successful!"}) 