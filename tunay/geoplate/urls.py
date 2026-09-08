from django.urls import include, path

from tunay.geoplate.views import GameView

app_name = 'geoplate'

urlpatterns = [
    path('', GameView.as_view(), name='index'),
    path('api/', include('tunay.geoplate.api.urls')),
]
