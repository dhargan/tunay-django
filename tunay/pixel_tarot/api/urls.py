from django.urls import path
from tunay.pixel_tarot.api import views

urlpatterns = [
    path('success/', views.success_view, name='api-success'),
] 