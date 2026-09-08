import random

from tunay.geoplate.models import City

MIN_PLATE_CODE = 1
MAX_PLATE_CODE = 81

# Wrong guesses allowed per plate code before the answer is revealed.
MAX_ATTEMPTS = 3


def pick_random_city(exclude_plate_code=None):
    """Return a random City, optionally avoiding the one already on screen."""
    plate_codes = list(
        City.objects.values_list('plate_code', flat=True)
    )
    if not plate_codes:
        return None

    candidates = [code for code in plate_codes if code != exclude_plate_code]
    chosen = random.choice(candidates or plate_codes)
    return City.objects.get(plate_code=chosen)


def parse_plate_code(value):
    """Return ``value`` as a valid plate code int, or ``None`` if it isn't one."""
    try:
        plate_code = int(value)
    except (TypeError, ValueError):
        return None
    if not MIN_PLATE_CODE <= plate_code <= MAX_PLATE_CODE:
        return None
    return plate_code


def parse_attempt(value):
    """Return the 1-based attempt number, clamped to the allowed range."""
    try:
        attempt = int(value)
    except (TypeError, ValueError):
        return 1
    return min(max(attempt, 1), MAX_ATTEMPTS)
