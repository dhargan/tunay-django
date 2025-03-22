class Card:
    def __init__(self, name, front_image_url, is_reversed=False):
        self.name = name        
        self.front_image_url = front_image_url
        self.back_image_url = 'pixel-tarot/assets/tarot__back.png'
        self.is_reversed = is_reversed

    def __str__(self):
        return f"{self.name}"
