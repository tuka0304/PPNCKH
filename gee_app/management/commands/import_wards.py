import json
from django.core.management.base import BaseCommand
from gee_app.models import Ward
from pathlib import Path

class Command(BaseCommand):
    help = 'Imports Ho Chi Minh City wards from a GeoJSON file.'

    def handle(self, *args, **options):
        # Path to the geojson we generated
        geojson_path = Path(__file__).resolve().parent.parent.parent.parent / 'gee_project' / 'hcmc_wards.geojson'
        
        if not geojson_path.exists():
            self.stdout.write(self.style.ERROR(f'File not found: {geojson_path}'))
            return

        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        features = data.get('features', [])
        count = 0
        for feature in features:
            props = feature['properties']
            geom = feature['geometry']
            
            ma_xa = props.get('maXa')
            ten_xa = props.get('tenXa')
            ma_huyen = props.get('maTinh_BNV') 
            
            # Bỏ qua Côn Đảo
            if ten_xa and 'Côn Đảo' in ten_xa:
                Ward.objects.filter(ten_xa__icontains='Côn Đảo').delete()
                continue
            
            Ward.objects.update_or_create(
                ma_xa=ma_xa,
                defaults={
                    'ten_xa': ten_xa,
                    'geometry': geom
                }
            )
            count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully imported {count} wards.'))
