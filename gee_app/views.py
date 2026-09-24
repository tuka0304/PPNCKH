from django.shortcuts import render, redirect
from .models import Ward, GEEDataRequest
from .gee_utils import start_drive_export, check_task_and_get_drive_link, delete_drive_file
from django.contrib import messages
import json
import os
import hashlib
from django.http import FileResponse, Http404

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
        
        # Prepare filename
        dataset_name = dataset.split('/')[-1]
        filename = f"{dataset_name}_{combined_ward.ten_xa}_{start_date}_{end_date}".replace(" ", "_")[:100]
        
        try:
            # Create Task in GEE
            task_id = start_drive_export(
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                geometry_geojson=combined_ward.geometry,
                filename=filename
            )
            
            # Save request to database
            req = GEEDataRequest.objects.create(
                ward=combined_ward,
                dataset=dataset,
                start_date=start_date,
                end_date=end_date,
                task_id=task_id,
                status='PROCESSING'
            )
            
            messages.success(request, f'Yêu cầu tải dữ liệu cho ({combined_ward.ten_xa}) đã được đưa vào hàng đợi xử lý.')
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
        filename = f"{dataset_name}_{req.ward.ten_xa}_{req.start_date}_{req.end_date}".replace(" ", "_")
        
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
