from django.urls import include, path

from tunay.portfolio import views

app_name = 'portfolio'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/', include('tunay.portfolio.api.urls')),
]
