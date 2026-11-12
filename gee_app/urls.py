from django.urls import path
from . import views

urlpatterns = [
    path('', views.thematic_map_view, name='home'),
    path('thematic-map/', views.thematic_map_view, name='thematic_map'),
    path('ban-tin/', views.trang_ban_tin, name='ban_tin'),
    path('portal/', views.landing_view, name='landing'),
    path('gee-download/', views.home_view, name='gee_download'),
    path('history/', views.history_view, name='history'),
    path('analysis/', views.analysis_view, name='analysis'),
    path('delete/<int:req_id>/', views.delete_file_view, name='delete_file'),
    path('api/get-map-layer/', views.get_map_layer, name='get_map_layer'),
    path('api/export-db/', views.export_db_csv, name='export_db_csv'),
    path('api/time-series/<int:req_id>/', views.api_get_time_series, name='api_get_time_series'),
    path('api/wards/geojson/', views.api_get_all_wards, name='api_get_all_wards'),
    path('api/thematic-map-data/', views.api_thematic_map_data, name='api_thematic_map_data'),
    path('api/danh-sach-phuong-xep-hang/', views.api_danh_sach_phuong_xep_hang, name='api_danh_sach_phuong_xep_hang'),
    path('api/dang-nhap-admin/', views.api_dang_nhap_admin, name='api_dang_nhap_admin'),
    path('api/dang-xuat-admin/', views.api_dang_xuat_admin, name='api_dang_xuat_admin'),
    path('api/trang-thai-phan-quyen/', views.api_trang_thai_phan_quyen, name='api_trang_thai_phan_quyen'),
    path('api/analysis-data/', views.api_analysis_data, name='api_analysis_data'),
    path('download-shapefile/', views.download_shapefile_view, name='download_shapefile'),
]
