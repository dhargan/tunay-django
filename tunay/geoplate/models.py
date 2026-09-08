from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class City(models.Model):
    """A Turkish province and its license plate code.

    Geometry deliberately lives outside the database: the polygons are served
    from the static GeoJSON asset and never touch this model.
    """

    name = models.CharField(max_length=64, unique=True)
    plate_code = models.PositiveSmallIntegerField(
        unique=True,
        validators=[MinValueValidator(1), MaxValueValidator(81)],
    )

    class Meta:
        verbose_name_plural = 'cities'
        ordering = ('plate_code',)

    @property
    def formatted_plate_code(self):
        return f'{self.plate_code:02d}'

    def __str__(self):
        return f'{self.formatted_plate_code} {self.name}'
