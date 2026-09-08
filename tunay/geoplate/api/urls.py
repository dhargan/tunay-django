from django.urls import path

from tunay.geoplate.api.views import CheckAnswerView, RandomPlateView

urlpatterns = [
    path('random-plate/', RandomPlateView.as_view(), name='geoplate-random-plate'),
    path('check-answer/', CheckAnswerView.as_view(), name='geoplate-check-answer'),
]
