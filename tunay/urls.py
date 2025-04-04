"""
URL configuration for tunay project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from tunay.home import views as home_views
from tunay.pixel_tarot import views as pixel_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_views.index),  # Ana sayfa için home app'i
    path('pixel-tarot/', pixel_views.index),  # pixel-tarot app'i için view
    path('api/pixel-tarot/', include('tunay.pixel_tarot.api.urls')),  # Pixel Tarot API
]
