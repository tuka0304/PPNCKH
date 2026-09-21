import geopandas as gpd
import json

def process():
    print("Loading shapefile...")
    df = gpd.read_file(r'e:\PPNCKH\Shapefile_Geodatabase\DiaPhan_Xa_2025.shp')
    print("Available tenTinh values:")
    # Filter for Ho Chi Minh City
    # Look for "Hồ Chí Minh" in tenTinh
    hcm = df[df['tenTinh'].str.contains('Hồ Chí Minh', na=False, case=False)]
    
    # Check if we got anything, if not maybe it's just 'Thành phố Hồ Chí Minh' or similar
    print(f"Found {len(hcm)} communes for Ho Chi Minh")
    
    if len(hcm) > 0:
        # Reproject to WGS84 (EPSG:4326) which is required for GEE
        hcm = hcm.to_crs(epsg=4326)
        
        # Save to GeoJSON
        out_path = r'e:\PPNCKH\gee_project\hcmc_wards.geojson'
        hcm.to_file(out_path, driver='GeoJSON')
        print(f"Saved GeoJSON to {out_path}")
        
if __name__ == '__main__':
    process()
