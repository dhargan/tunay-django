class Card:
    def __init__(self, name, front_image_url, is_reversed=False):
        self.name = name        
        self.front_image_url = front_image_url
        self.back_image_url = "{% static 'pixel-tarot/assets/tarot_back.png' %}"
        self.is_reversed = is_reversed

    def __str__(self):
        return f"{self.name} ({'Reversed' if self.is_reversed else 'Upright'})"




