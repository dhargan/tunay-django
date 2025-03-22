import json
import random
from django.contrib.staticfiles.storage import staticfiles_storage


class Card:
    def __init__(self, name, front_image_url, is_reversed=False):
        self.name = name
        self.front_image_url = front_image_url
        self.is_reversed = is_reversed

    def __str__(self):
        position = "Reversed" if self.is_reversed else "Upright"
        return f"{self.name} ({position})"


class DeckManager:
    def __init__(self, language='en'):
        self.language = language
        self.cards = self.load_tarot_cards()[language]

    def load_tarot_cards(self):
        with staticfiles_storage.open('pixel-tarot/data/tarot_cards.json') as file:
            data = json.load(file)
        return data

    def pick_random_card(self):
        random_card_data = random.choice(self.cards)        
        card = Card(
            name=random_card_data['name'],
            front_image_url=random_card_data['front_image_url'],
            is_reversed = random.choice([True, False])
        )
        return card

    def pick_unique_cards(self, count=9):
        if count > len(self.cards):
            raise ValueError(f"Cannot pick {count} unique cards from a deck of {len(self.cards)} cards")
        
        # Kartları kopyala ve karıştır
        available_cards = self.cards.copy()
        random.shuffle(available_cards)
        
        unique_cards = []
        while len(unique_cards) < count:
            card_data = available_cards.pop()
            card = Card(
                name=card_data['name'],
                front_image_url=card_data['front_image_url'],
                is_reversed=random.choice([True, False])
            )
            unique_cards.append(card)
            
        return unique_cards
