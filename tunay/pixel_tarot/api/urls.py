from django.urls import path
from tunay.pixel_tarot.api import views

urlpatterns = [
    path('interpret/', views.interpret, name='api-interpret'),
] 