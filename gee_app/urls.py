from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('history/', views.history_view, name='history'),
    path('delete/<int:req_id>/', views.delete_file_view, name='delete_file'),
]
