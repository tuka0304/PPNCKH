import json
from django.core.management.base import BaseCommand
from gee_app.models import Ward
import os
import hashlib

class Command(BaseCommand):
    help = 'Seeds Ho Chi Minh City wards from geojson, excluding Con Dao'

    def handle(self, *args, **options):
        # We will use the hcmc_wards.geojson that was created earlier.
        # Alternatively, we could read the shapefile if we had geopandas installed,
        # but using geojson is standard and lighter for Django.
        
        file_path = os.path.join('e:\\', 'PPNCKH', 'gee_project', 'hcmc_wards.geojson')
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        features = data.get('features', [])
        self.stdout.write(f'Found {len(features)} features in GeoJSON')

        created_count = 0
        skipped_count = 0

        for feature in features:
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            
            # The properties in DiaPhan_Xa_2025 usually have tenXa, tenHuyen, tenTinh
            ten_xa = props.get('tenXa', '')
            ten_huyen = props.get('tenHuyen', '')
            
            # Logic: exclude Côn Đảo
            if 'Côn Đảo' in ten_xa or 'Con Dao' in ten_xa or 'Côn Đảo' in ten_huyen or 'Con Dao' in ten_huyen:
                self.stdout.write(self.style.WARNING(f'Skipped Con Dao'))
                skipped_count += 1
                continue
                
            if not ten_xa:
                continue

            # Generate ma_xa if not provided
            ma_xa = props.get('maXa')
            if not ma_xa:
                # Fallback to hash if ma_xa is missing
                ma_xa = "HCM_" + hashlib.md5(f"{ten_xa}_{ten_huyen}".encode()).hexdigest()[:8]

            ward, created = Ward.objects.get_or_create(
                ma_xa=ma_xa,
                defaults={
                    'ten_xa': ten_xa,
                    'geometry': geom
                }
            )

            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {created_count} wards. Skipped {skipped_count}.'))
