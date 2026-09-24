from django.db import models

class Ward(models.Model):
    ma_xa = models.CharField(max_length=50, unique=True, verbose_name="Mã Xã")
    ten_xa = models.CharField(max_length=255, verbose_name="Tên Xã/Phường")
    # Store GeoJSON geometry as a JSON field
    geometry = models.JSONField(verbose_name="Geometry (GeoJSON)")

    def __str__(self):
        return f"{self.ten_xa}"

class GEEDataRequest(models.Model):
    DATASET_CHOICES = [
        ('LANDSAT/LC08/C02/T1_TOA', 'Landsat 8 TOA'),
        ('COPERNICUS/S2_SR_HARMONIZED', 'Sentinel-2 SR'),
    ]
    
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="requests", verbose_name="Khu Vực")
    dataset = models.CharField(max_length=100, choices=DATASET_CHOICES, verbose_name="Loại Dữ Liệu")
    start_date = models.DateField(verbose_name="Từ Ngày")
    end_date = models.DateField(verbose_name="Đến Ngày")
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian yêu cầu")
    task_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="GEE Task ID")
    drive_file_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Google Drive File ID")
    download_url = models.URLField(max_length=1000, blank=True, null=True, verbose_name="Link Tải GEE")
    status = models.CharField(max_length=20, default='PENDING', verbose_name="Trạng Thái")
    
    # Interpretation Indices
    ndvi_mean = models.FloatField(blank=True, null=True, verbose_name="NDVI Trung bình")
    ndwi_mean = models.FloatField(blank=True, null=True, verbose_name="NDWI Trung bình")
    ndbi_mean = models.FloatField(blank=True, null=True, verbose_name="NDBI Trung bình")

    def __str__(self):
        return f"{self.dataset} - {self.ward.ten_xa} ({self.start_date} to {self.end_date})"
