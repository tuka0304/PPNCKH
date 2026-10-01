from django.shortcuts import render, redirect
from .models import Ward, GEEDataRequest
from django.http import FileResponse, Http404, JsonResponse
from .gee_utils import start_drive_export, check_task_and_get_drive_link, delete_drive_file, get_map_tile_url
from django.contrib import messages
import json
import os
import hashlib
import unicodedata
import re
import csv
from django.http import HttpResponse

def slugify_filename(text):
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-zA-Z0-9.\-_]', '_', text)
    return re.sub(r'_+', '_', text).strip('_')

def get_bounds_for_geometries(geometries):
    min_lon, min_lat, max_lon, max_lat = float('inf'), float('inf'), float('-inf'), float('-inf')
    
    def extract_coords(coords):
        nonlocal min_lon, min_lat, max_lon, max_lat
        if isinstance(coords[0], (int, float)):
            lon, lat = coords[0], coords[1]
            if lon < min_lon: min_lon = lon
            if lat < min_lat: min_lat = lat
            if lon > max_lon: max_lon = lon
            if lat > max_lat: max_lat = lat
        else:
            for item in coords:
                extract_coords(item)
                
    for geom in geometries:
        if 'coordinates' in geom:
            extract_coords(geom['coordinates'])
            
    if min_lon == float('inf'):
        return None
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat]
        ]]
    }

def home_view(request):
    datasets = GEEDataRequest.DATASET_CHOICES
    
    if request.method == 'POST':
        ward_names_input = request.POST.get('ward_names')
        dataset = request.POST.get('dataset')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        
        # Parse names
        names = [n.strip() for n in ward_names_input.split(',') if n.strip()]
        
        # Query wards
        found_wards = list(Ward.objects.filter(ten_xa__in=names))
        
        if not found_wards:
            messages.error(request, 'Không tìm thấy Xã/Phường nào trong cơ sở dữ liệu phù hợp với tên bạn nhập. Hãy chắc chắn bạn đã nhập đúng chính tả (VD: "Phường 1").')
            return redirect('home')
            
        # Create a combined virtual ward if multiple selected
        if len(found_wards) == 1:
            combined_ward = found_wards[0]
        else:
            combined_name = ", ".join([w.ten_xa for w in found_wards])
            combined_ward = Ward.objects.filter(ten_xa=combined_name).first()
            if not combined_ward:
                combined_geom = {
                    "type": "GeometryCollection",
                    "geometries": [w.geometry for w in found_wards]
                }
                # Create a pseudo-ward to link to GEEDataRequest
                ma_xa_hash = "CTM_" + hashlib.md5(combined_name.encode()).hexdigest()[:8]
                combined_ward = Ward.objects.create(
                    ma_xa=ma_xa_hash,
                    ten_xa=combined_name,
                    geometry=combined_geom
                )
        
        # Prepare filename and folder name
        dataset_name = dataset.split('/')[-1]
        ward_slug = slugify_filename(combined_ward.ten_xa)
        filename = f"{dataset_name}_{ward_slug}_{start_date}_{end_date}"[:100]
        folder_name = ward_slug
        
        # 1. CHECK CACHE: See if we already downloaded this exact image
        existing_req = GEEDataRequest.objects.filter(
            ward=combined_ward,
            dataset=dataset,
            start_date=start_date,
            end_date=end_date,
            status='COMPLETED'
        ).first()

        if existing_req and existing_req.csv_download_url:
            # Duplicate the record and reuse data instantly (Only if CSV is also cached)
            GEEDataRequest.objects.create(
                ward=combined_ward,
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                task_id=existing_req.task_id, # Keep same task ID
                status='COMPLETED',
                download_url=existing_req.download_url,
                csv_download_url=existing_req.csv_download_url,
                drive_file_id=existing_req.drive_file_id,
                ndvi_mean=existing_req.ndvi_mean,
                ndwi_mean=existing_req.ndwi_mean,
                ndbi_mean=existing_req.ndbi_mean,
                lst_mean=existing_req.lst_mean,
                dem_mean=existing_req.dem_mean
            )
            messages.success(request, f'Dữ liệu ({combined_ward.ten_xa}) đã có sẵn trong kho lưu trữ! Trích xuất ngay lập tức mà không cần tải lại từ Earth Engine.')
            return redirect('history')
            
        try:
            # Generate direct download URL in GEE and calculate indices
            download_url, csv_url, ndvi, ndwi, ndbi, lst, dem = start_drive_export(
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                geometry_geojson=combined_ward.geometry,
                filename=filename,
                folder_name=folder_name
            )
            
            # Save request to database
            req = GEEDataRequest.objects.create(
                ward=combined_ward,
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                task_id="DIRECT_DOWNLOAD",
                status='COMPLETED',
                download_url=download_url,
                csv_download_url=csv_url,
                ndvi_mean=ndvi,
                ndwi_mean=ndwi,
                ndbi_mean=ndbi,
                lst_mean=lst,
                dem_mean=dem
            )
            
            messages.success(request, f'Yêu cầu tải dữ liệu cho ({combined_ward.ten_xa}) đã được xử lý và có thể tải ngay lập tức! (Kèm Chỉ số phân tích)')
            return redirect('history')
            
        except Exception as e:
            messages.error(request, f'Lỗi khi gọi GEE API: {e}')
    
    return render(request, 'gee_app/home.html', {
        'datasets': datasets
    })

def history_view(request):
    # Check status of PROCESSING requests
    processing_requests = GEEDataRequest.objects.filter(status='PROCESSING')
    for req in processing_requests:
        dataset_name = req.dataset.split('/')[-1]
        ward_slug = slugify_filename(req.ward.ten_xa)
        filename = f"{dataset_name}_{ward_slug}_{req.start_date}_{req.end_date}"[:100]
        
        try:
            status, link, file_id = check_task_and_get_drive_link(req.task_id, filename)
            if status == 'COMPLETED' and link:
                req.status = 'COMPLETED'
                req.download_url = link
                req.drive_file_id = file_id
                req.save()
            elif status == 'FAILED':
                req.status = 'FAILED'
                req.save()
        except Exception as e:
            print(f"Error checking task {req.task_id}: {e}")
            pass

    requests = GEEDataRequest.objects.all().order_by('-requested_at')
    return render(request, 'gee_app/history.html', {'requests': requests})

def delete_file_view(request, req_id):
    if request.method == 'POST':
        try:
            req = GEEDataRequest.objects.get(id=req_id)
            if req.drive_file_id:
                success = delete_drive_file(req.drive_file_id)
                if success:
                    messages.success(request, 'Đã xóa file trên Google Drive thành công để giải phóng dung lượng!')
                    # Clear the URL and file_id from DB
                    req.download_url = None
                    req.drive_file_id = None
                    req.status = 'DELETED'
                    req.save()
                else:
                    messages.error(request, 'Không thể xóa file. Vui lòng thử lại.')
        except GEEDataRequest.DoesNotExist:
            pass
    return redirect('history')

def download_shapefile_view(request):
    # Offload bandwidth to Google Drive
    drive_link = 'https://drive.google.com/drive/folders/1pvKAvOkqBSAcaVf0IBGAZhXXBAbcvxgt?usp=sharing'
    return redirect(drive_link)

def landing_view(request):
    return render(request, 'gee_app/landing.html')

def analysis_view(request):
    return render(request, 'gee_app/analysis.html')

def get_map_layer(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ward_names_input = data.get('ward_names', '')
            dataset = data.get('dataset')
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            layer_type = data.get('layer_type', 'NDVI')
            
            names = [n.strip() for n in ward_names_input.split(',') if n.strip()]
            found_wards = list(Ward.objects.filter(ten_xa__in=names))
            
            if not found_wards:
                return JsonResponse({'error': 'Không tìm thấy xã'}, status=400)
                
            if len(found_wards) == 1:
                geometry = found_wards[0].geometry
            elif len(found_wards) <= 5:
                geometry = {
                    "type": "GeometryCollection",
                    "geometries": [w.geometry for w in found_wards]
                }
            else:
                geometry = get_bounds_for_geometries([w.geometry for w in found_wards])
                
            tile_url = get_map_tile_url(
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                geometry_geojson=geometry,
                layer_type=layer_type
            )
            return JsonResponse({'tile_url': tile_url})
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=400)
d e f   e x p o r t _ d b _ c s v ( r e q u e s t ) : 
         r e s p o n s e   =   H t t p R e s p o n s e ( c o n t e n t _ t y p e = ' t e x t / c s v ' ) 
         r e s p o n s e [ ' C o n t e n t - D i s p o s i t i o n ' ]   =   ' a t t a c h m e n t ;   f i l e n a m e = \  
 d a t a _ w a r e h o u s e _ e x p o r t . c s v \ ' 
         r e s p o n s e . w r i t e ( u ' \ u f e f f ' . e n c o d e ( ' u t f 8 ' ) ) 
 
         w r i t e r   =   c s v . w r i t e r ( r e s p o n s e ) 
         w r i t e r . w r i t e r o w ( [ 
                 ' K h u   V u c ' ,   ' L o a i   D u   L i e u ' ,   ' T u   N g a y ' ,   ' D e n   N g a y ' ,   ' T h o i   G i a n   Y e u   C a u ' ,   
                 ' T r a n g   T h a i ' ,   ' N D V I   T r u n g   B i n h ' ,   ' N D W I   T r u n g   B i n h ' ,   ' N D B I   T r u n g   B i n h ' ,   
                 ' L S T   T r u n g   B i n h   ( C ) ' ,   ' D E M   T r u n g   B i n h   ( m ) ' 
         ] ) 
 
         r e q u e s t s   =   G E E D a t a R e q u e s t . o b j e c t s . a l l ( ) . o r d e r _ b y ( ' - r e q u e s t e d _ a t ' ) 
         f o r   r e q   i n   r e q u e s t s : 
                 w r i t e r . w r i t e r o w ( [ 
                         r e q . w a r d . t e n _ x a , 
                         r e q . g e t _ d a t a s e t _ d i s p l a y ( ) , 
                         r e q . s t a r t _ d a t e . s t r f t i m e ( ' % Y - % m - % d ' ) , 
                         r e q . e n d _ d a t e . s t r f t i m e ( ' % Y - % m - % d ' ) , 
                         r e q . r e q u e s t e d _ a t . s t r f t i m e ( ' % Y - % m - % d   % H : % M : % S ' ) , 
                         r e q . s t a t u s , 
                         r e q . n d v i _ m e a n , 
                         r e q . n d w i _ m e a n , 
                         r e q . n d b i _ m e a n , 
                         r e q . l s t _ m e a n , 
                         r e q . d e m _ m e a n 
                 ] ) 
 
         r e t u r n   r e s p o n s e  
 