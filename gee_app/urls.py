from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('app/', views.home_view, name='home'),
    path('history/', views.history_view, name='history'),
    path('analysis/', views.analysis_view, name='analysis'),
    path('delete/<int:req_id>/', views.delete_file_view, name='delete_file'),
    path('api/get-map-layer/', views.get_map_layer, name='get_map_layer'),
    path('download-shapefile/', views.download_shapefile_view, name='download_shapefile'),
]
