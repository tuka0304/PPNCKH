from django.shortcuts import render, redirect
from .models import Ward, GEEDataRequest, IndexType, DataOrigin, ObservationData
from datetime import datetime
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
            combined_name_full = ", ".join([w.ten_xa for w in found_wards])
            if len(combined_name_full) > 250:
                combined_name = f"Nhiều khu vực ({len(found_wards)} phường/xã)"
            else:
                combined_name = combined_name_full
                
            combined_ward = Ward.objects.filter(ten_xa=combined_name).first()
            if not combined_ward:
                combined_geom = {
                    "type": "GeometryCollection",
                    "geometries": [w.geometry for w in found_wards]
                }
                # Create a pseudo-ward to link to GEEDataRequest
                ma_xa_hash = "CTM_" + hashlib.md5(combined_name_full.encode()).hexdigest()[:8]
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
            # Create a pending request
            req = GEEDataRequest.objects.create(
                ward=combined_ward,
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                task_id="DIRECT_DOWNLOAD",
                status='PROCESSING'
            )
            
            # Define a background task function
            def background_gee_task(request_id, ds, s_date, e_date, geom, fname, folder, ward_id):
                try:
                    # Execute long-running GEE call
                    download_url, time_series_data, ndvi, ndwi, ndbi, lst, dem = start_drive_export(
                        dataset=ds,
                        start_date=s_date,
                        end_date=e_date,
                        geometry_geojson=geom,
                        filename=fname,
                        folder_name=folder
                    )
                    
                    # Update request
                    req_obj = GEEDataRequest.objects.get(id=request_id)
                    req_obj.download_url = download_url
                    req_obj.ndvi_mean = ndvi
                    req_obj.ndwi_mean = ndwi
                    req_obj.ndbi_mean = ndbi
                    req_obj.lst_mean = lst
                    req_obj.dem_mean = dem
                    
                    # Save Time Series Data
                    if time_series_data:
                        origin, _ = DataOrigin.objects.get_or_create(code='GEE_CURRENT', defaults={'name': 'Dữ liệu Hiện Trạng GEE'})
                        observations = []
                        
                        # Fetch the ward again to get a fresh connection in this thread
                        ward_obj = Ward.objects.get(id=ward_id)
                        
                        for dp in time_series_data:
                            idx_type, _ = IndexType.objects.get_or_create(code=dp['Index'], defaults={'name': dp['Index']})
                            try:
                                obs_time = datetime.strptime(dp['Date'], '%Y-%m-%d').date()
                                observations.append(ObservationData(
                                    request_ref=req_obj,
                                    ward=ward_obj,
                                    index_type=idx_type,
                                    origin=origin,
                                    observation_time=obs_time,
                                    value=dp['Value']
                                ))
                            except Exception:
                                pass
                        if observations:
                            ObservationData.objects.bulk_create(observations)
                    
                    req_obj.status = 'COMPLETED'
                    req_obj.save()
                    
                except Exception as e:
                    print(f"Background GEE Task Error: {e}")
                    req_obj = GEEDataRequest.objects.get(id=request_id)
                    req_obj.status = 'FAILED'
                    req_obj.save()

            # Start thread
            import threading
            thread = threading.Thread(target=background_gee_task, args=(
                req.id, dataset, start_date, end_date, combined_ward.geometry, filename, folder_name, combined_ward.id
            ))
            thread.daemon = True
            thread.start()
            
            messages.success(request, f'Yêu cầu tải dữ liệu cho khu vực đã được đưa vào hàng đợi xử lý ngầm (để tránh quá tải Server). Vui lòng đợi vài phút và tải lại trang Lịch sử để xem kết quả.')
            return redirect('history')
            
        except Exception as e:
            messages.error(request, f'Lỗi khởi tạo yêu cầu: {e}')
    
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
def export_db_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="data_warehouse_export.csv"'
    response.write(u'\ufeff'.encode('utf8')) # BOM for Excel

    writer = csv.writer(response)
    writer.writerow([
        'Khu Vực', 'Loại Dữ Liệu', 'Từ Ngày', 'Đến Ngày', 'Thời Gian Yêu Cầu', 
        'Trạng Thái', 'NDVI Trung bình', 'NDWI Trung bình', 'NDBI Trung bình', 
        'LST Trung bình (°C)', 'DEM Trung bình (m)'
    ])

    requests = GEEDataRequest.objects.all().order_by('-requested_at')
    for req in requests:
        writer.writerow([
            req.ward.ten_xa,
            req.get_dataset_display(),
            req.start_date.strftime('%Y-%m-%d'),
            req.end_date.strftime('%Y-%m-%d'),
            req.requested_at.strftime('%Y-%m-%d %H:%M:%S'),
            req.status,
            req.ndvi_mean,
            req.ndwi_mean,
            req.ndbi_mean,
            req.lst_mean,
            req.dem_mean
        ])


def api_get_time_series(request, req_id):
    try:
        req = GEEDataRequest.objects.get(id=req_id)
        
        # Lấy dữ liệu time series đã lưu trong database
        observations = ObservationData.objects.filter(request_ref=req).order_by('observation_time')
        
        data = []
        for obs in observations:
            data.append({
                'Date': obs.observation_time.strftime('%Y-%m-%d'),
                'Index': obs.index_type.code,
                'Value': obs.value
            })
            
        return JsonResponse({'status': 'success', 'data': data})
    except GEEDataRequest.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy yêu cầu!'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
