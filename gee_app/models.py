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
        ('SRTM_DEM', 'Mô Hình Độ Cao (SRTM DEM 30m)'),
        ('L8_LST', 'Nhiệt Độ Bề Mặt (Landsat 8 LST)'),
    ]
    
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="requests", verbose_name="Khu Vực")
    dataset = models.CharField(max_length=100, choices=DATASET_CHOICES, verbose_name="Loại Dữ Liệu")
    start_date = models.DateField(verbose_name="Từ Ngày")
    end_date = models.DateField(verbose_name="Đến Ngày")
    requested_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian yêu cầu")
    task_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="GEE Task ID")
    drive_file_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Google Drive File ID")
    download_url = models.URLField(max_length=1000, blank=True, null=True, verbose_name="Link Tải GEE")
    csv_download_url = models.URLField(max_length=1000, blank=True, null=True, verbose_name="Link Tải CSV Chỉ Số")
    status = models.CharField(max_length=20, default='PENDING', verbose_name="Trạng Thái")
    
    # Interpretation Indices
    ndvi_mean = models.FloatField(blank=True, null=True, verbose_name="NDVI Trung bình")
    ndwi_mean = models.FloatField(blank=True, null=True, verbose_name="NDWI Trung bình")
    ndbi_mean = models.FloatField(blank=True, null=True, verbose_name="NDBI Trung bình")
    lst_mean = models.FloatField(blank=True, null=True, verbose_name="Nhiệt Độ Trung bình (°C)")
    dem_mean = models.FloatField(blank=True, null=True, verbose_name="Độ Cao Trung bình (m)")

    def __str__(self):
        return f"{self.dataset} - {self.ward.ten_xa} ({self.start_date} to {self.end_date})"

class IndexType(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="Mã Chỉ Số")
    name = models.CharField(max_length=100, verbose_name="Tên Chỉ Số")
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.code

class DataOrigin(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="Mã Nguồn")
    name = models.CharField(max_length=100, verbose_name="Tên Nguồn")
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.code

class ObservationData(models.Model):
    request_ref = models.ForeignKey(GEEDataRequest, on_delete=models.CASCADE, related_name="observations", null=True, blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="observations")
    index_type = models.ForeignKey(IndexType, on_delete=models.CASCADE)
    origin = models.ForeignKey(DataOrigin, on_delete=models.CASCADE)
    observation_time = models.DateField(verbose_name="Thời Gian")
    value = models.FloatField(verbose_name="Giá Trị", null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['observation_time']),
            models.Index(fields=['index_type', 'origin', 'ward']),
        ]
