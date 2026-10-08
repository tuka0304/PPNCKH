with open('gee_app/views.py', 'rb') as f:
    content = f.read()

# find the index of "return JsonResponse({'error': 'Invalid method'}, status=400)"
idx = content.find(b"return JsonResponse({'error': 'Invalid method'}, status=400)")
if idx != -1:
    content = content[:idx + len(b"return JsonResponse({'error': 'Invalid method'}, status=400)\r\n")]

with open('gee_app/views.py', 'wb') as f:
    f.write(content)
    
with open('gee_app/views.py', 'a', encoding='utf-8') as f:
    f.write('''
def export_db_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="data_warehouse_export.csv"'
    response.write(u'\\ufeff'.encode('utf8')) # BOM for Excel

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

    return response
''')
