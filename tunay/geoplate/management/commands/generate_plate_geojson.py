"""Enrich the raw province GeoJSON with plate codes from the City table.

Run once (and again whenever the source file or the city data changes):

    python manage.py generate_plate_geojson
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from tunay.geoplate.models import City
from tunay.geoplate.normalization import match_key, normalize_name

GEOJSON_DIR = Path(__file__).resolve().parents[2] / 'static' / 'geoplate' / 'geojson'
DEFAULT_SOURCE = GEOJSON_DIR / 'tr-cities.json'
DEFAULT_TARGET = GEOJSON_DIR / 'tr-cities-with-plate.json'


class Command(BaseCommand):
    help = 'Writes a copy of the province GeoJSON with plate_code added to each feature.'

    def add_arguments(self, parser):
        parser.add_argument('--source', default=str(DEFAULT_SOURCE))
        parser.add_argument('--target', default=str(DEFAULT_TARGET))

    def handle(self, *args, **options):
        source = Path(options['source'])
        target = Path(options['target'])

        if not source.exists():
            raise CommandError(f'Source GeoJSON not found: {source}')

        cities = list(City.objects.all())
        if not cities:
            raise CommandError(
                'No City rows found. Load them first: '
                'python manage.py loaddata geoplate_cities'
            )

        by_key = {match_key(city.name): city for city in cities}

        with source.open(encoding='utf-8') as handle:
            collection = json.load(handle)

        features = collection.get('features') or []
        matched, unmatched = 0, []
        seen_keys = set()

        for feature in features:
            properties = feature.setdefault('properties', {})
            raw_name = properties.get('name') or ''
            official_name = normalize_name(raw_name)
            city = by_key.get(match_key(official_name))

            if city is None:
                unmatched.append(raw_name or '<unnamed feature>')
                continue

            properties['name'] = city.name
            properties['plate_code'] = city.plate_code
            seen_keys.add(match_key(city.name))
            matched += 1

        for raw_name in unmatched:
            self.stderr.write(
                self.style.WARNING(
                    f'No City match for GeoJSON province "{raw_name}" - '
                    'add it to GEOJSON_NAME_OVERRIDES in tunay/geoplate/normalization.py'
                )
            )

        missing_cities = sorted(
            city.name for city in cities if match_key(city.name) not in seen_keys
        )
        if missing_cities:
            self.stderr.write(self.style.WARNING(
                f'{len(missing_cities)} cities have no polygon in the GeoJSON: '
                + ', '.join(missing_cities)
            ))

        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('w', encoding='utf-8') as handle:
            json.dump(collection, handle, ensure_ascii=False, separators=(',', ':'))

        self.stdout.write(self.style.SUCCESS(
            f'Wrote {target} - {matched}/{len(features)} features enriched, '
            f'{len(unmatched)} unmatched.'
        ))
