import os
import sys
import json
import urllib.request
import subprocess
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gee_project.settings')
django.setup()

import ee
from gee_app.gee_utils import init_gee

def khoi_tao_he_thong():
    init_gee()

def tai_anh_tu_gee(hinh_anh, vung_chon, ti_le=400):
    duong_dan_tai = hinh_anh.getDownloadURL({
        'scale': ti_le,
        'region': vung_chon,
        'format': 'GEO_TIFF'
    })
    return duong_dan_tai

def day_tep_len_minio(duong_dan_cuc_bo, duong_dan_dich_minio):
    ten_tep_tam = os.path.basename(duong_dan_cuc_bo)
    duong_dan_container = f"/tmp/{ten_tep_tam}"
    subprocess.run(["docker", "cp", duong_dan_cuc_bo, f"pnnckh_minio:{duong_dan_container}"], check=True, capture_output=True)
    subprocess.run(["docker", "exec", "pnnckh_minio", "mc", "cp", duong_dan_container, f"local/hcmc-images/{duong_dan_dich_minio}"], check=True, capture_output=True)
    subprocess.run(["docker", "exec", "pnnckh_minio", "rm", duong_dan_container], check=True, capture_output=True)

def xu_ly_dong_bo_toan_bo_anh():
    khoi_tao_he_thong()
    vung_chon = ee.Geometry.BBox(106.35, 10.35, 107.05, 11.15)
    thu_muc_tam = os.path.join(os.path.dirname(__file__), "thu_muc_tam_anh")
    os.makedirs(thu_muc_tam, exist_ok=True)
    
    danh_sach_sieu_du_lieu = []

    anh_dem = ee.Image('USGS/SRTMGL1_003').clip(vung_chon)
    url_dem = tai_anh_tu_gee(anh_dem, vung_chon, 300)
    tep_dem_tam = os.path.join(thu_muc_tam, "srtm_dem_hcmc_30m.tif")
    urllib.request.urlretrieve(url_dem, tep_dem_tam)
    day_tep_len_minio(tep_dem_tam, "dem/srtm_dem_hcmc_30m.tif")
    danh_sach_sieu_du_lieu.append({
        "ten_tep": "dem/srtm_dem_hcmc_30m.tif",
        "loai_chi_so": "DEM",
        "cam_bien": "SRTM GL1",
        "nam": 2000,
        "kich_thuoc_bytes": os.path.getsize(tep_dem_tam),
        "he_toa_do": "EPSG:4326"
    })
    os.remove(tep_dem_tam)

    cac_nam = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    for nam in cac_nam:
        ngay_bat_dau = f"{nam}-01-01"
        ngay_ket_thuc = f"{nam}-04-30" if nam < 2026 else "2026-03-31"

        tap_anh_s2 = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                      .filterBounds(vung_chon)
                      .filterDate(ngay_bat_dau, ngay_ket_thuc)
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 35))
                      .median()
                      .clip(vung_chon))

        anh_ndvi = tap_anh_s2.normalizedDifference(['B8', 'B4']).rename('NDVI')
        url_ndvi = tai_anh_tu_gee(anh_ndvi, vung_chon, 400)
        tep_ndvi_tam = os.path.join(thu_muc_tam, f"ndvi_hcmc_{nam}.tif")
        urllib.request.urlretrieve(url_ndvi, tep_ndvi_tam)
        day_tep_len_minio(tep_ndvi_tam, f"ndvi/ndvi_hcmc_{nam}.tif")
        danh_sach_sieu_du_lieu.append({
            "ten_tep": f"ndvi/ndvi_hcmc_{nam}.tif",
            "loai_chi_so": "NDVI",
            "cam_bien": "Sentinel-2 MSI",
            "nam": nam,
            "kich_thuoc_bytes": os.path.getsize(tep_ndvi_tam),
            "he_toa_do": "EPSG:4326"
        })
        os.remove(tep_ndvi_tam)

        tap_anh_l8 = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
                      .filterBounds(vung_chon)
                      .filterDate(ngay_bat_dau, ngay_ket_thuc)
                      .filter(ee.Filter.lt('CLOUD_COVER', 40))
                      .median()
                      .clip(vung_chon))

        anh_lst = tap_anh_l8.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('LST')
        url_lst = tai_anh_tu_gee(anh_lst, vung_chon, 400)
        tep_lst_tam = os.path.join(thu_muc_tam, f"lst_hcmc_{nam}.tif")
        urllib.request.urlretrieve(url_lst, tep_lst_tam)
        day_tep_len_minio(tep_lst_tam, f"lst/lst_hcmc_{nam}.tif")
        danh_sach_sieu_du_lieu.append({
            "ten_tep": f"lst/lst_hcmc_{nam}.tif",
            "loai_chi_so": "LST",
            "cam_bien": "Landsat-8 TIRS",
            "nam": nam,
            "kich_thuoc_bytes": os.path.getsize(tep_lst_tam),
            "he_toa_do": "EPSG:4326"
        })
        os.remove(tep_lst_tam)

        if nam in [2021, 2023, 2025]:
            anh_tvdi = anh_lst.subtract(22.0).divide(18.0).rename('TVDI')
            url_tvdi = tai_anh_tu_gee(anh_tvdi, vung_chon, 400)
            tep_tvdi_tam = os.path.join(thu_muc_tam, f"tvdi_hcmc_{nam}.tif")
            urllib.request.urlretrieve(url_tvdi, tep_tvdi_tam)
            day_tep_len_minio(tep_tvdi_tam, f"tvdi/tvdi_hcmc_{nam}.tif")
            danh_sach_sieu_du_lieu.append({
                "ten_tep": f"tvdi/tvdi_hcmc_{nam}.tif",
                "loai_chi_so": "TVDI",
                "cam_bien": "Landsat-8 & S2 Fusion",
                "nam": nam,
                "kich_thuoc_bytes": os.path.getsize(tep_tvdi_tam),
                "he_toa_do": "EPSG:4326"
            })
            os.remove(tep_tvdi_tam)

        if nam in [2022, 2024, 2026]:
            anh_ndwi = tap_anh_s2.normalizedDifference(['B3', 'B8']).rename('NDWI')
            url_ndwi = tai_anh_tu_gee(anh_ndwi, vung_chon, 400)
            tep_ndwi_tam = os.path.join(thu_muc_tam, f"ndwi_hcmc_{nam}.tif")
            urllib.request.urlretrieve(url_ndwi, tep_ndwi_tam)
            day_tep_len_minio(tep_ndwi_tam, f"ndwi/ndwi_hcmc_{nam}.tif")
            danh_sach_sieu_du_lieu.append({
                "ten_tep": f"ndwi/ndwi_hcmc_{nam}.tif",
                "loai_chi_so": "NDWI",
                "cam_bien": "Sentinel-2 MSI",
                "nam": nam,
                "kich_thuoc_bytes": os.path.getsize(tep_ndwi_tam),
                "he_toa_do": "EPSG:4326"
            })
            os.remove(tep_ndwi_tam)

        if nam in [2020, 2023, 2026]:
            anh_ndbi = tap_anh_s2.normalizedDifference(['B11', 'B8']).rename('NDBI')
            url_ndbi = tai_anh_tu_gee(anh_ndbi, vung_chon, 400)
            tep_ndbi_tam = os.path.join(thu_muc_tam, f"ndbi_hcmc_{nam}.tif")
            urllib.request.urlretrieve(url_ndbi, tep_ndbi_tam)
            day_tep_len_minio(tep_ndbi_tam, f"ndbi/ndbi_hcmc_{nam}.tif")
            danh_sach_sieu_du_lieu.append({
                "ten_tep": f"ndbi/ndbi_hcmc_{nam}.tif",
                "loai_chi_so": "NDBI",
                "cam_bien": "Sentinel-2 MSI",
                "nam": nam,
                "kich_thuoc_bytes": os.path.getsize(tep_ndbi_tam),
                "he_toa_do": "EPSG:4326"
            })
            os.remove(tep_ndbi_tam)

    tap_anh_s2_goc = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                      .filterBounds(vung_chon)
                      .filterDate('2024-01-01', '2024-03-31')
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
                      .median()
                      .clip(vung_chon))
    anh_s2_rgb = tap_anh_s2_goc.select(['B4', 'B3', 'B2'])
    url_s2 = tai_anh_tu_gee(anh_s2_rgb, vung_chon, 500)
    tep_s2_tam = os.path.join(thu_muc_tam, "s2_rgb_hcmc_2024.tif")
    urllib.request.urlretrieve(url_s2, tep_s2_tam)
    day_tep_len_minio(tep_s2_tam, "sentinel_2/s2_rgb_hcmc_2024.tif")
    danh_sach_sieu_du_lieu.append({
        "ten_tep": "sentinel_2/s2_rgb_hcmc_2024.tif",
        "loai_chi_so": "RGB",
        "cam_bien": "Sentinel-2 MSI",
        "nam": 2024,
        "kich_thuoc_bytes": os.path.getsize(tep_s2_tam),
        "he_toa_do": "EPSG:4326"
    })
    os.remove(tep_s2_tam)

    tep_catalog = os.path.join(thu_muc_tam, "catalog_du_lieu_ve_tinh_hcmc.json")
    with open(tep_catalog, "w", encoding="utf-8") as file_json:
        json.dump({
            "stac_version": "1.0.0",
            "id": "hcmc-satellite-bigdata-lakehouse",
            "title": "Kho Dữ Liệu Lớn Ảnh Viễn Thám TP. Hồ Chí Minh",
            "description": "Tập hợp các tệp ảnh vệ tinh GeoTIFF đa thời gian (2020-2026) lưu trữ trên Object Storage MinIO",
            "extent": {
                "spatial": [106.35, 10.35, 107.05, 11.15],
                "temporal": ["2020-01-01T00:00:00Z", "2026-03-31T23:59:59Z"]
            },
            "tong_so_tep": len(danh_sach_sieu_du_lieu),
            "danh_sach_tep": danh_sach_sieu_du_lieu
        }, file_json, ensure_ascii=False, indent=2)
    day_tep_len_minio(tep_catalog, "catalog/catalog_du_lieu_ve_tinh_hcmc.json")
    os.remove(tep_catalog)

    tep_csv = os.path.join(thu_muc_tam, "danh_muc_anh_ve_tinh.csv")
    with open(tep_csv, "w", encoding="utf-8") as file_csv:
        file_csv.write("ten_tep,loai_chi_so,cam_bien,nam,kich_thuoc_bytes,he_toa_do\n")
        for item in danh_sach_sieu_du_lieu:
            file_csv.write(f"{item['ten_tep']},{item['loai_chi_so']},{item['cam_bien']},{item['nam']},{item['kich_thuoc_bytes']},{item['he_toa_do']}\n")
    day_tep_len_minio(tep_csv, "metadata/danh_muc_anh_ve_tinh.csv")
    os.remove(tep_csv)

    if os.path.exists(thu_muc_tam):
        os.rmdir(thu_muc_tam)

    print(f"HOAN_TAT_NAP_DU_LIEU: {len(danh_sach_sieu_du_lieu)} tep da duoc nap thanh cong vao MinIO hcmc-images")

if __name__ == "__main__":
    xu_ly_dong_bo_toan_bo_anh()
