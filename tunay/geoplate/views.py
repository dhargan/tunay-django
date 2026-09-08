from django.views.generic import TemplateView

from tunay.geoplate.services import pick_random_city


class GameView(TemplateView):
    template_name = 'geoplate/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['city'] = pick_random_city()
        return context
