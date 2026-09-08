"""Province name normalization between the GeoJSON asset and the City table.

The GeoJSON (source: cihadturhan/tr-geojson) carries short/alternative province
names in ``properties.name``, so they have to be translated to the official
names stored in :class:`~tunay.geoplate.models.City` before matching.
"""

# GeoJSON name -> official City.name
GEOJSON_NAME_OVERRIDES = {
    'Afyon': 'Afyonkarahisar',
    'Hakkari': 'Hakkâri',
    'Maras': 'Kahramanmaraş',
    'Urfa': 'Şanlıurfa',
    'Icel': 'Mersin',
    'İçel': 'Mersin',
}

# Characters that differ between the ASCII-ish and the Turkish spelling of a name.
_FOLD_MAP = str.maketrans({
    'ı': 'i',
    'İ': 'i',
    'ş': 's',
    'ğ': 'g',
    'ü': 'u',
    'ö': 'o',
    'ç': 'c',
    'â': 'a',
    'î': 'i',
    'û': 'u',
})


def normalize_name(name: str) -> str:
    """Return the official province name for a raw GeoJSON name."""
    cleaned = ' '.join(name.split())
    return GEOJSON_NAME_OVERRIDES.get(cleaned, cleaned)


def match_key(name: str) -> str:
    """Return a diacritic-insensitive key usable for fuzzy name comparison."""
    return ' '.join(name.split()).lower().translate(_FOLD_MAP)
