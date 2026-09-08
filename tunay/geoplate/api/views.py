from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from tunay.geoplate.models import City
from tunay.geoplate.services import parse_plate_code, pick_random_city


class GeoplateThrottle(ScopedRateThrottle):
    scope = 'geoplate'


class RandomPlateView(APIView):
    """Hands the frontend the next plate code to ask about.

    The province name is intentionally left out of the payload: it is the
    answer the player is supposed to find on the map.
    """

    throttle_classes = [GeoplateThrottle]

    def get(self, request):
        exclude = parse_plate_code(request.query_params.get('exclude'))
        city = pick_random_city(exclude_plate_code=exclude)
        if city is None:
            return Response(
                {'detail': 'No cities loaded. Run: manage.py loaddata geoplate_cities'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({
            'plate_code': city.plate_code,
            'plate_code_display': city.formatted_plate_code,
        })


class CheckAnswerView(APIView):
    """Compares the clicked province's plate code with the asked one.

    Both codes come from the request, so no game state is kept server-side.
    """

    throttle_classes = [GeoplateThrottle]

    def post(self, request):
        asked = parse_plate_code(request.data.get('asked_plate_code'))
        clicked = parse_plate_code(request.data.get('clicked_plate_code'))

        if asked is None or clicked is None:
            return Response(
                {'detail': 'asked_plate_code and clicked_plate_code must be integers in 1-81.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        correct = asked == clicked
        payload = {'correct': correct}

        if correct:
            city = City.objects.filter(plate_code=asked).first()
            if city is not None:
                payload['city_name'] = city.name

        return Response(payload)
