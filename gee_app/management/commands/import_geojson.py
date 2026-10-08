import json
import os
from django.core.management.base import BaseCommand
from django.conf import settings
from gee_app.models import Ward

class Command(BaseCommand):
    help = 'Imports HCMC wards GeoJSON into PostgreSQL database'

    def handle(self, *args, **kwargs):
        file_path = os.path.join(settings.BASE_DIR, 'gee_app', 'static', 'data', 'hcmc_wards.geojson')
        
        self.stdout.write(f"Reading {file_path}...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        count = 0
        for feature in data.get('features', []):
            properties = feature.get('properties', {})
            ma_xa = properties.get('maXa')
            ten_xa = properties.get('tenXa')
            geometry = feature.get('geometry')
            
            if ma_xa and ten_xa and geometry:
                Ward.objects.update_or_create(
                    ma_xa=ma_xa,
                    defaults={
                        'ten_xa': ten_xa,
                        'geometry': geometry
                    }
                )
                count += 1
                
        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count} wards into Postgres.'))
