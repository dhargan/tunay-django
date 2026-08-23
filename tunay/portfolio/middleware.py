from urllib.parse import urlencode

from django.http import HttpResponseRedirect
from django.urls import reverse


class PortfolioSuperuserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/portfolio/'):
            user = request.user
            if not (user.is_authenticated and user.is_superuser):
                login_url = reverse('admin:login')
                query = urlencode({'next': request.get_full_path()})
                return HttpResponseRedirect(f'{login_url}?{query}')
        return self.get_response(request)
