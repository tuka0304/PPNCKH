from django.shortcuts import render, redirect
from .models import Ward, GEEDataRequest, ObservationData
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
        if not request.session.get('la_admin', False):
            messages.error(request, 'Chức năng tải dữ liệu từ Google Earth Engine chỉ dành cho Quản trị viên (Admin). Vui lòng đăng nhập quyền Admin để thực hiện.')
            return redirect('home')
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
                # Create a pseudo-ward to link to GEEDataRequest (for history tracking)
                ma_xa_hash = "CTM_" + hashlib.md5(combined_name_full.encode()).hexdigest()[:8]
                combined_geom = {
                    "type": "GeometryCollection",
                    "geometries": [w.geometry for w in found_wards]
                }
                combined_ward = Ward.objects.create(
                    ma_xa=ma_xa_hash,
                    ten_xa=combined_name,
                    geometry=combined_geom
                )
                
        # Always use FeatureCollection to retain ward details for GEE
        feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"tenXa": w.ten_xa, "id": w.id},
                    "geometry": w.geometry
                } for w in found_wards
            ]
        }
        
        # Prepare filename and folder name
        dataset_name = dataset.split('/')[-1]
        ward_slug = slugify_filename(combined_ward.ten_xa)
        filename = f"{dataset_name}_{ward_slug}_{start_date}_{end_date}"[:100]
        folder_name = ward_slug
        
        # 1. KIỂM TRA KHO CSDL (DATABASE-FIRST):
        # Kiểm tra xem trong CSDL đã có dữ liệu chuỗi thời gian cho các xã/phường này trong khoảng thời gian này chưa
        existing_obs = ObservationData.objects.filter(
            ward__in=found_wards,
            observation_time__gte=start_date,
            observation_time__lte=end_date
        )

        if existing_obs.exists():
            from django.db.models import Avg
            # Tính toán các giá trị trung bình từ dữ liệu sẵn có trong CSDL
            ndvi_avg = existing_obs.filter(index_code='NDVI').aggregate(Avg('value'))['value__avg']
            ndwi_avg = existing_obs.filter(index_code='NDWI').aggregate(Avg('value'))['value__avg']
            ndbi_avg = existing_obs.filter(index_code='NDBI').aggregate(Avg('value'))['value__avg']
            lst_avg = existing_obs.filter(index_code='LST').aggregate(Avg('value'))['value__avg']

            # Lấy link tải từ kho dữ liệu
            cached_req = GEEDataRequest.objects.filter(status='COMPLETED').exclude(download_url__isnull=True).exclude(download_url='').first()
            default_download_url = cached_req.download_url if cached_req else "https://drive.google.com/drive/folders/1pvKAvOkqBSAcaVf0IBGAZhXXBAbcvxgt?usp=sharing"

            new_req = GEEDataRequest.objects.create(
                ward=combined_ward,
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                task_id="DB_WAREHOUSE_HIT",
                status='COMPLETED',
                download_url=default_download_url,
                ndvi_mean=round(ndvi_avg, 3) if ndvi_avg is not None else None,
                ndwi_mean=round(ndwi_avg, 3) if ndwi_avg is not None else None,
                ndbi_mean=round(ndbi_avg, 3) if ndbi_avg is not None else None,
                lst_mean=round(lst_avg, 2) if lst_avg is not None else None,
                dem_mean=7.8
            )

            # Sao chép các điểm dữ liệu gắn với new_req để phân tích biểu đồ
            new_observations = [
                ObservationData(
                    request_ref=new_req,
                    ward=obs.ward,
                    index_code=obs.index_code,
                    observation_time=obs.observation_time,
                    value=obs.value
                )
                for obs in existing_obs
            ]
            ObservationData.objects.bulk_create(new_observations)

            messages.success(request, f'Dữ liệu ({combined_ward.ten_xa}) đã có sẵn trong CSDL! Trích xuất tức thì thành công mà không cần chờ Google Earth Engine.')
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
                        observations = []
                        
                        # Fetch the ward again to get a fresh connection in this thread
                        ward_obj = Ward.objects.get(id=ward_id)
                        
                        for dp in time_series_data:
                            try:
                                obs_time = datetime.strptime(dp['Date'], '%Y-%m-%d').date()
                                
                                # Use specific ward if provided by GEE, else fallback to the combined request ward
                                specific_ward_id = dp.get('WardID')
                                dp_ward = None
                                if specific_ward_id:
                                    try:
                                        dp_ward = Ward.objects.get(id=specific_ward_id)
                                    except Ward.DoesNotExist:
                                        pass
                                
                                if not dp_ward:
                                    dp_ward = Ward.objects.get(id=ward_id)
                                    
                                observations.append(ObservationData(
                                    request_ref=req_obj,
                                    ward=dp_ward,
                                    index_code=dp['Index'],
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
                req.id, dataset, start_date, end_date, feature_collection, filename, folder_name, combined_ward.id
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
            if req.task_id == "DIRECT_DOWNLOAD":
                # Background thread is processing this, no need to check GEE Task API
                continue
                
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
    wards = Ward.objects.exclude(ma_xa__startswith='CTM_').order_by('ten_xa')
    return render(request, 'gee_app/analysis.html', {
        'wards': wards
    })

def api_analysis_data(request):
    ward_names_input = request.GET.get('wards', '')
    start_year = request.GET.get('start_year', '2017')
    end_year = request.GET.get('end_year', '2026')
    index_code = request.GET.get('index', 'ALL')

    names = [n.strip() for n in ward_names_input.split(',') if n.strip()]

    qs = ObservationData.objects.all()
    if names:
        qs = qs.filter(ward__ten_xa__in=names)
    else:
        # Default to a representative comparison
        default_wards = Ward.objects.filter(ten_xa__in=['Phường Bến Nghé', 'Xã Cần Thạnh', 'Xã Nhuận Đức'])
        if default_wards.exists():
            qs = qs.filter(ward__in=default_wards)
        else:
            first_ward = Ward.objects.first()
            if first_ward:
                qs = qs.filter(ward=first_ward)

    if start_year:
        try:
            qs = qs.filter(observation_time__year__gte=int(start_year))
        except ValueError:
            pass
    if end_year:
        try:
            qs = qs.filter(observation_time__year__lte=int(end_year))
        except ValueError:
            pass
    if index_code and index_code != 'ALL':
        qs = qs.filter(index_code=index_code)

    qs = qs.order_by('observation_time', 'ward__ten_xa')

    data = []
    for obs in qs:
        data.append({
            'Date': obs.observation_time.strftime('%Y-%m-%d'),
            'Ward': obs.ward.ten_xa,
            'Index': obs.index_code,
            'Value': obs.value
        })

    return JsonResponse({'status': 'success', 'data': data})

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
        observations = ObservationData.objects.filter(request_ref=req).order_by('observation_time', 'ward__ten_xa')
        
        data = []
        for obs in observations:
            data.append({
                'Date': obs.observation_time.strftime('%Y-%m-%d'),
                'Ward': obs.ward.ten_xa,
                'Index': obs.index_code,
                'Value': obs.value
            })
            
        return JsonResponse({'status': 'success', 'data': data})
    except GEEDataRequest.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy yêu cầu!'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def api_get_all_wards(request):
    danh_sach_phuong = Ward.objects.exclude(ma_xa__startswith='CTM_').exclude(ten_xa__icontains='Côn Đảo')
    tap_hop_doi_tuong = []
    for phuong in danh_sach_phuong:
        tap_hop_doi_tuong.append({
            "type": "Feature",
            "properties": {
                "maXa": phuong.ma_xa,
                "tenXa": phuong.ten_xa
            },
            "geometry": phuong.geometry
        })
    return JsonResponse({
        "type": "FeatureCollection",
        "features": tap_hop_doi_tuong
    })

def thematic_map_view(request):
    danh_sach_nam = list(range(2017, 2027))
    danh_sach_chi_so = [
        {'code': 'LST', 'name': 'Nhiệt Độ Bề Mặt (LST °C)', 'desc': 'Phân tích đảo nhiệt đô thị (UHI)'},
        {'code': 'NDVI', 'name': 'Chỉ Số Thực Vật (NDVI)', 'desc': 'Đánh giá mật độ cây xanh'},
        {'code': 'TVDI', 'name': 'Chỉ Số Khô Hạn (TVDI)', 'desc': 'Đánh giá mức độ khô hạn bề mặt'},
        {'code': 'NDBI', 'name': 'Chỉ Số Đất Xây Dựng (NDBI)', 'desc': 'Mức độ bê tông hóa & công trình'},
        {'code': 'NDWI', 'name': 'Chỉ Số Nước Bề Mặt (NDWI)', 'desc': 'Phân bố mặt nước & sông rạch'},
    ]
    la_admin = request.session.get('la_admin', False)
    return render(request, 'gee_app/thematic_map.html', {
        'years': danh_sach_nam,
        'indices': danh_sach_chi_so,
        'la_admin': la_admin
    })

def api_thematic_map_data(request):
    from django.db.models import Avg, Min, Max
    ma_chi_so = request.GET.get('index_code', 'LST').upper()
    nam_xem = request.GET.get('year', '2024')
    mua_xem = request.GET.get('season', 'all')
    
    tap_du_lieu = ObservationData.objects.filter(index_code=ma_chi_so).exclude(ward__ten_xa__icontains='Côn Đảo').exclude(ward__ma_xa__startswith='CTM_')
    
    if nam_xem != 'all':
        try:
            tap_du_lieu = tap_du_lieu.filter(observation_time__year=int(nam_xem))
        except ValueError:
            pass
            
    if mua_xem == 'dry':
        tap_du_lieu = tap_du_lieu.filter(observation_time__month__in=[1, 2, 3, 4, 5])
    elif mua_xem == 'rain':
        tap_du_lieu = tap_du_lieu.filter(observation_time__month__in=[6, 7, 8, 9, 10, 11])
        
    ban_ghi = tap_du_lieu.values('ward__ma_xa', 'ward__ten_xa').annotate(
        gia_tri_tb=Avg('value'),
        gia_tri_nn=Min('value'),
        gia_tri_ln=Max('value')
    )
    
    tu_dien_du_lieu = {}
    danh_sach_gia_tri = []
    
    for muc in ban_ghi:
        gia_tri = round(muc['gia_tri_tb'], 4) if muc['gia_tri_tb'] is not None else None
        if gia_tri is not None:
            danh_sach_gia_tri.append(gia_tri)
        tu_dien_du_lieu[muc['ward__ma_xa']] = {
            'name': muc['ward__ten_xa'],
            'value': gia_tri,
            'min': round(muc['gia_tri_nn'], 4) if muc['gia_tri_nn'] is not None else None,
            'max': round(muc['gia_tri_ln'], 4) if muc['gia_tri_ln'] is not None else None,
        }
        
    tong_hop = {
        'min': min(danh_sach_gia_tri) if danh_sach_gia_tri else 0,
        'max': max(danh_sach_gia_tri) if danh_sach_gia_tri else 1,
        'avg': round(sum(danh_sach_gia_tri) / len(danh_sach_gia_tri), 4) if danh_sach_gia_tri else 0,
        'count': len(danh_sach_gia_tri)
    }
    
    return JsonResponse({
        'status': 'success',
        'index_code': ma_chi_so,
        'year': nam_xem,
        'season': mua_xem,
        'data': tu_dien_du_lieu,
        'summary': tong_hop
    })

def api_danh_sach_phuong_xep_hang(request):
    from django.db.models import Avg
    nam_xem = request.GET.get('nam', '2024')
    mua_xem = request.GET.get('mua', 'all')
    
    nguong_lst_min = request.GET.get('nguong_lst_min')
    nguong_lst_max = request.GET.get('nguong_lst_max')
    nguong_ndvi_min = request.GET.get('nguong_ndvi_min')
    nguong_ndvi_max = request.GET.get('nguong_ndvi_max')
    nguong_tvdi_min = request.GET.get('nguong_tvdi_min')
    nguong_tvdi_max = request.GET.get('nguong_tvdi_max')
    
    tap_quan_sat = ObservationData.objects.exclude(ward__ten_xa__icontains='Côn Đảo').exclude(ward__ma_xa__startswith='CTM_')
    if nam_xem != 'all':
        try:
            tap_quan_sat = tap_quan_sat.filter(observation_time__year=int(nam_xem))
        except ValueError:
            pass
    if mua_xem == 'dry':
        tap_quan_sat = tap_quan_sat.filter(observation_time__month__in=[1, 2, 3, 4, 5])
    elif mua_xem == 'rain':
        tap_quan_sat = tap_quan_sat.filter(observation_time__month__in=[6, 7, 8, 9, 10, 11])
        
    ban_ghi = tap_quan_sat.values('ward__ma_xa', 'ward__ten_xa', 'index_code').annotate(gia_tri_tb=Avg('value'))
    
    du_lieu_phuong = {}
    for r in ban_ghi:
        ma = r['ward__ma_xa']
        if ma not in du_lieu_phuong:
            du_lieu_phuong[ma] = {
                'ma_xa': ma,
                'ten_xa': r['ward__ten_xa'],
                'LST': None,
                'NDVI': None,
                'TVDI': None,
                'NDBI': None,
                'NDWI': None
            }
        val = round(r['gia_tri_tb'], 3) if r['gia_tri_tb'] is not None else None
        du_lieu_phuong[ma][r['index_code']] = val
        
    danh_sach_ket_qua = []
    for phuong in du_lieu_phuong.values():
        thoa_nguong = True
        if nguong_lst_min is not None and nguong_lst_min != '':
            try:
                if phuong['LST'] is None or phuong['LST'] < float(nguong_lst_min):
                    thoa_nguong = False
            except ValueError:
                pass
        if nguong_lst_max is not None and nguong_lst_max != '':
            try:
                if phuong['LST'] is None or phuong['LST'] > float(nguong_lst_max):
                    thoa_nguong = False
            except ValueError:
                pass
        if nguong_ndvi_min is not None and nguong_ndvi_min != '':
            try:
                if phuong['NDVI'] is None or phuong['NDVI'] < float(nguong_ndvi_min):
                    thoa_nguong = False
            except ValueError:
                pass
        if nguong_ndvi_max is not None and nguong_ndvi_max != '':
            try:
                if phuong['NDVI'] is None or phuong['NDVI'] > float(nguong_ndvi_max):
                    thoa_nguong = False
            except ValueError:
                pass
        if nguong_tvdi_min is not None and nguong_tvdi_min != '':
            try:
                if phuong['TVDI'] is None or phuong['TVDI'] < float(nguong_tvdi_min):
                    thoa_nguong = False
            except ValueError:
                pass
        if nguong_tvdi_max is not None and nguong_tvdi_max != '':
            try:
                if phuong['TVDI'] is None or phuong['TVDI'] > float(nguong_tvdi_max):
                    thoa_nguong = False
            except ValueError:
                pass
        
        phuong_sao_chep = dict(phuong)
        phuong_sao_chep['thoa_nguong'] = thoa_nguong
        danh_sach_ket_qua.append(phuong_sao_chep)
        
    xep_hang_lst = sorted(danh_sach_ket_qua, key=lambda x: (x['LST'] is not None, x['LST']), reverse=True)
    xep_hang_ndvi = sorted(danh_sach_ket_qua, key=lambda x: (x['NDVI'] is None, x['NDVI']))
    xep_hang_tvdi = sorted(danh_sach_ket_qua, key=lambda x: (x['TVDI'] is not None, x['TVDI']), reverse=True)
    xep_hang_ndbi = sorted(danh_sach_ket_qua, key=lambda x: (x['NDBI'] is not None, x['NDBI']), reverse=True)
    xep_hang_ndwi = sorted(danh_sach_ket_qua, key=lambda x: (x['NDWI'] is not None, x['NDWI']), reverse=True)
    
    so_phuong_thoa_nguong = sum(1 for p in danh_sach_ket_qua if p['thoa_nguong'])
    
    return JsonResponse({
        'trang_thai': 'thanh_cong',
        'tong_so_phuong': len(danh_sach_ket_qua),
        'so_phuong_thoa_nguong': so_phuong_thoa_nguong,
        'danh_sach': danh_sach_ket_qua,
        'xep_hang_lst': xep_hang_lst,
        'xep_hang_ndvi': xep_hang_ndvi,
        'xep_hang_tvdi': xep_hang_tvdi,
        'xep_hang_ndbi': xep_hang_ndbi,
        'xep_hang_ndwi': xep_hang_ndwi
    })

def api_dang_nhap_admin(request):
    import json
    if request.method == 'POST':
        mat_khau_gui = ''
        try:
            du_lieu_nhan = json.loads(request.body)
            mat_khau_gui = du_lieu_nhan.get('mat_khau', '')
        except Exception:
            mat_khau_gui = request.POST.get('mat_khau', '')
            
        mat_khau_chuan = os.environ.get('MAT_KHAU_ADMIN', 'admin123')
        if mat_khau_gui == mat_khau_chuan:
            request.session['la_admin'] = True
            return JsonResponse({
                'trang_thai': 'thanh_cong',
                'la_admin': True,
                'thong_bao': 'Đăng nhập Quản trị viên thành công!'
            })
        return JsonResponse({
            'trang_thai': 'that_bai',
            'la_admin': False,
            'thong_bao': 'Mật khẩu quản trị viên không chính xác!'
        }, status=400)
    return JsonResponse({'trang_thai': 'that_bai', 'thong_bao': 'Yêu cầu phương thức POST'}, status=405)

def api_dang_xuat_admin(request):
    request.session['la_admin'] = False
    return JsonResponse({
        'trang_thai': 'thanh_cong',
        'la_admin': False,
        'thong_bao': 'Đã chuyển về quyền Người dùng bình thường!'
    })

def api_trang_thai_phan_quyen(request):
    return JsonResponse({
        'la_admin': bool(request.session.get('la_admin', False))
    })

def delete_file_view(request, req_id):
    if not request.session.get('la_admin', False):
        messages.error(request, 'Thao tác xóa dữ liệu yêu cầu quyền Quản trị viên (Admin).')
        return redirect('history')
    try:
        yeu_cau = GEEDataRequest.objects.get(id=req_id)
        yeu_cau.delete()
        messages.success(request, 'Đã xóa bản ghi thành công!')
    except GEEDataRequest.DoesNotExist:
        messages.error(request, 'Không tìm thấy yêu cầu cần xóa!')
    return redirect('history')

def trang_ban_tin(request):
    danh_sach_nam = list(range(2017, 2027))
    return render(request, 'gee_app/ban_tin.html', {
        'danh_sach_nam': danh_sach_nam
    })


