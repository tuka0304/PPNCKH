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
    
    if dataset == 'SRTM_DEM':
        # DEM is a single static image
        image = ee.Image('USGS/SRTMGL1_003').clip(roi)
        
        # Calculate mean elevation
        stats = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=30,
            maxPixels=1e13
        ).getInfo()
        
        dem_mean = stats.get('elevation')
        
        # Generate TIF download link
        download_url = image.getDownloadURL({
            'name': filename,
            'scale': 30,
            'region': roi,
            'format': 'GEO_TIFF'
        })
        
        return download_url, None, None, None, None, None, dem_mean
        
    # For time-series datasets
    collection = ee.ImageCollection(dataset)\
        .filterBounds(roi)\
        .filterDate(str(start_date), str(end_date))
    
    if 'LANDSAT' in dataset and dataset != 'L8_LST':
        collection = collection.filter(ee.Filter.lt('CLOUD_COVER', 20))
    elif 'S2' in dataset:
        collection = collection.filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    # L8_LST doesn't have a standard CLOUD_COVER in C02 L2 in the same way, but we can filter by CLOUD_COVER if available or just use QA_PIXEL. For simplicity, we just filter by cloud cover if possible.
    elif dataset == 'L8_LST':
        def mask_clouds(img):
            qa = img.select('QA_PIXEL')
            # Bit 3 is cloud, Bit 4 is cloud shadow
            cloud = qa.bitwiseAnd(1 << 3).eq(0)
            shadow = qa.bitwiseAnd(1 << 4).eq(0)
            return img.updateMask(cloud.And(shadow))
            
        collection = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")\
            .filterBounds(roi)\
            .filterDate(str(start_date), str(end_date))\
            .filter(ee.Filter.lt('CLOUD_COVER', 20))\
            .map(mask_clouds)
    else:
        collection = collection.filter(ee.Filter.eq('system:index', '0'))
        
    # Check if collection is empty
    if collection.size().getInfo() == 0:
        raise Exception("Không có bức ảnh nào chụp khu vực này thỏa mãn điều kiện trong khoảng thời gian bạn chọn.")
        
    if dataset == 'L8_LST':
        def calculate_lst(img):
            # L8 ST is in ST_B10. scale = 0.00341802, offset = 149.0
            lst = img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('LST')
            return img.addBands(lst)
        collection = collection.map(calculate_lst)
        image = collection.select(['LST']).median().clip(roi).float()
    else:
        image = collection.median().clip(roi).float()
    
    # ---------------------------------------------------------
    # Generate direct download URL instead of Drive Task
    # ---------------------------------------------------------
    try:
        download_url = image.getDownloadURL({
            'name': filename,
            'scale': 30 if 'LANDSAT' in dataset else 10,
            'region': roi,
            'format': 'GEO_TIFF'
        })
    except Exception as e:
        print(f"Error generating download URL: {e}")
        raise Exception("Không thể tạo link tải ảnh. Có thể kích thước ảnh quá lớn, hãy chọn khu vực nhỏ hơn.")
    
    # ---------------------------------------------------------
    # TIME SERIES EXTRACTION FOR CSV & MEAN STATS
    # ---------------------------------------------------------
    def extract_indices(img):
        date = ee.Date(img.get('system:time_start')).format('yyyy-MM-dd')
        
        if 'LANDSAT' in dataset and dataset != 'L8_LST':
            ndvi = img.normalizedDifference(['B5', 'B4']).rename('NDVI')
            ndwi = img.normalizedDifference(['B3', 'B5']).rename('NDWI')
            ndbi = img.normalizedDifference(['B6', 'B5']).rename('NDBI')
            indices_img = ee.Image.cat([ndvi, ndwi, ndbi])
        elif 'S2' in dataset:
            ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
            ndwi = img.normalizedDifference(['B3', 'B8']).rename('NDWI')
            ndbi = img.normalizedDifference(['B11', 'B8']).rename('NDBI')
            indices_img = ee.Image.cat([ndvi, ndwi, ndbi])
        elif dataset == 'L8_LST':
            indices_img = img.select(['LST'])
            
        stats = indices_img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=100,
            maxPixels=1e13
        )
        
        feature_dict = {'Date': date}
        if dataset == 'L8_LST':
            feature_dict['LST'] = stats.get('LST')
        else:
            feature_dict['NDVI'] = stats.get('NDVI')
            feature_dict['NDWI'] = stats.get('NDWI')
            feature_dict['NDBI'] = stats.get('NDBI')
            
        return ee.Feature(None, feature_dict)

    csv_url = None
    try:
        time_series_fc = ee.FeatureCollection(collection.map(extract_indices))
        if dataset == 'L8_LST':
            csv_url = time_series_fc.getDownloadURL(filetype='CSV', selectors=['Date', 'LST'], filename=filename + "_LST")
        else:
            csv_url = time_series_fc.getDownloadURL(filetype='CSV', selectors=['Date', 'NDVI', 'NDWI', 'NDBI'], filename=filename + "_Indices")
    except Exception as e:
        print(f"Error generating CSV URL: {e}")
    
    ndvi_mean = None
    ndwi_mean = None
    ndbi_mean = None
    lst_mean = None
    dem_mean = None
    
    try:
        if dataset == 'L8_LST':
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=roi,
                scale=100,
                maxPixels=1e13
            ).getInfo()
            lst_mean = stats.get('LST')
        else:
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
    
    return download_url, csv_url, ndvi_mean, ndwi_mean, ndbi_mean, lst_mean, dem_mean

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
