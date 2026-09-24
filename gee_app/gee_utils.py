import ee
import os
from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Global initialization flag
_is_initialized = False

def init_gee():
    global _is_initialized
    if not _is_initialized:
        try:
            sa = getattr(settings, 'GEE_SERVICE_ACCOUNT', None) or os.environ.get('GEE_SERVICE_ACCOUNT')
            key_path = getattr(settings, 'GEE_PRIVATE_KEY_PATH', None) or os.environ.get('GEE_PRIVATE_KEY_PATH')
            
            if sa and key_path:
                credentials = ee.ServiceAccountCredentials(sa, key_path)
                ee.Initialize(credentials=credentials)
            else:
                ee.Initialize(project='your-project-id') # Fallback
            _is_initialized = True
        except Exception as e:
            print(f"Error initializing GEE: {e}")
            raise e

def get_drive_service():
    key_path = getattr(settings, 'GEE_PRIVATE_KEY_PATH', None) or os.environ.get('GEE_PRIVATE_KEY_PATH')
    if key_path and os.path.exists(key_path):
        SCOPES = ['https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds)
    return None

def start_drive_export(dataset, start_date, end_date, geometry_geojson, filename, folder_name):
    init_gee()
    
    # Convert GeoJSON geometry to ee.Geometry
    roi = ee.Geometry(geometry_geojson)
    
    # Load dataset
    collection = ee.ImageCollection(dataset)\
        .filterBounds(roi)\
        .filterDate(str(start_date), str(end_date))
    
    if 'LANDSAT' in dataset:
        collection = collection.filter(ee.Filter.lt('CLOUD_COVER', 20))
    elif 'S2' in dataset:
        collection = collection.filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    else:
        collection = collection.filter(ee.Filter.eq('system:index', '0'))
        
    # Check if collection is empty
    if collection.size().getInfo() == 0:
        raise Exception("Không có bức ảnh nào chụp khu vực này thỏa mãn điều kiện (không bị mây che) trong khoảng thời gian bạn chọn. Vui lòng chọn khoảng thời gian dài hơn!")
        
    image = collection.median().clip(roi).float()
    
    # We MUST use a single shared folder because Service Accounts don't have Drive quota
    SHARED_FOLDER = "PPNCKH_GEE"
    
    # Start Export Task
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=filename,
        folder=SHARED_FOLDER,
        fileNamePrefix=filename,
        scale=30 if 'LANDSAT' in dataset else 10,
        region=roi,
        maxPixels=1e13
    )
    task.start()
    
    # ---------------------------------------------------------
    # TIME SERIES EXTRACTION FOR CSV
    # ---------------------------------------------------------
    def extract_indices(img):
        date = ee.Date(img.get('system:time_start')).format('YYYY-MM-DD')
        
        if 'LANDSAT' in dataset:
            ndvi = img.normalizedDifference(['B5', 'B4']).rename('NDVI')
            ndwi = img.normalizedDifference(['B3', 'B5']).rename('NDWI')
            ndbi = img.normalizedDifference(['B6', 'B5']).rename('NDBI')
        else:
            ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
            ndwi = img.normalizedDifference(['B3', 'B8']).rename('NDWI')
            ndbi = img.normalizedDifference(['B11', 'B8']).rename('NDBI')
            
        indices = ee.Image.cat([ndvi, ndwi, ndbi])
        
        stats = indices.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=100,
            maxPixels=1e13
        )
        
        return ee.Feature(None, {
            'Date': date,
            'NDVI': stats.get('NDVI'),
            'NDWI': stats.get('NDWI'),
            'NDBI': stats.get('NDBI')
        })

    try:
        time_series_fc = collection.map(extract_indices)
        csv_task = ee.batch.Export.table.toDrive(
            collection=time_series_fc,
            description=filename + "_CSV",
            folder=SHARED_FOLDER,
            fileNamePrefix=filename + "_Indices",
            fileFormat='CSV'
        )
        csv_task.start()
    except Exception as e:
        print(f"Error starting CSV task: {e}")
    
    ndvi_mean = None
    ndwi_mean = None
    ndbi_mean = None
    
    try:
        if 'LANDSAT' in dataset:
            ndvi_img = image.normalizedDifference(['B5', 'B4']).rename('NDVI')
            ndwi_img = image.normalizedDifference(['B3', 'B5']).rename('NDWI')
            ndbi_img = image.normalizedDifference(['B6', 'B5']).rename('NDBI')
        elif 'S2' in dataset:
            ndvi_img = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            ndwi_img = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
            ndbi_img = image.normalizedDifference(['B11', 'B8']).rename('NDBI')
            
        indices = ee.Image.cat([ndvi_img, ndwi_img, ndbi_img])
        stats = indices.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=100, # Using 100m scale for faster computation
            maxPixels=1e13
        ).getInfo()
        
        ndvi_mean = stats.get('NDVI')
        ndwi_mean = stats.get('NDWI')
        ndbi_mean = stats.get('NDBI')
    except Exception as e:
        print(f"Error calculating indices: {e}")
    
    return task.id, ndvi_mean, ndwi_mean, ndbi_mean

def check_task_and_get_drive_link(task_id, filename):
    init_gee()
    tasks = ee.data.getTaskStatus(task_id)
    if not tasks:
        return 'FAILED', None, None
        
    state = tasks[0].get('state')
    
    if state == 'COMPLETED':
        # Find file in drive
        service = get_drive_service()
        if not service:
            return 'COMPLETED', None, None
            
        results = service.files().list(
            q=f"name='{filename}.tif' and trashed=false",
            fields="files(id, webViewLink, webContentLink)",
            spaces='drive'
        ).execute()
        
        items = results.get('files', [])
        if not items:
            return 'COMPLETED', None, None
            
        file_id = items[0]['id']
        link = items[0].get('webContentLink') or items[0].get('webViewLink')
        
        # Share to anyone
        service.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        return 'COMPLETED', link, file_id
        
    elif state in ['FAILED', 'CANCELLED']:
        return 'FAILED', None, None
    else:
        # READY, RUNNING
        return 'PROCESSING', None, None

def delete_drive_file(file_id):
    service = get_drive_service()
    if service and file_id:
        try:
            service.files().delete(fileId=file_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting file {file_id}: {e}")
    return False
