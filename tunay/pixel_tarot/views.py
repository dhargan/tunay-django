from django.shortcuts import render

from tunay.pixel_tarot.cards import DeckManager


def index(request):
    deck = DeckManager()
    cards = deck.pick_unique_cards(10)
    return render(request, 'pixel_tarot/index.html', {'cards': cards})
