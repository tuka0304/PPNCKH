-- ==============================================================================
-- SCRIPT DỌN DẸP BẢNG THỪA & ĐỒNG BỘ CSDL POSTGRESQL (PGADMIN / SUPABASE)
-- Dự án: Website Quản lý & Trích xuất Dữ liệu Vệ tinh GEE TP. Hồ Chí Minh
-- ==============================================================================

-- 1. XÓA CÁC BẢNG KHÔNG LIÊN QUAN / THỬ NGHIỆM KHÔNG DÙNG ĐẾN
DROP TABLE IF EXISTS aggregated_statistics CASCADE;
DROP TABLE IF EXISTS observation_data_2024 CASCADE;
DROP TABLE IF EXISTS observation_data_2025 CASCADE;
DROP TABLE IF EXISTS observation_data_2026 CASCADE;
DROP TABLE IF EXISTS spatial_regions CASCADE;
DROP TABLE IF EXISTS data_origins CASCADE;
DROP TABLE IF EXISTS index_types CASCADE;

-- Xóa các bảng Auth / Admin mặc định của Django (Dự án không có đăng nhập/admin)
DROP TABLE IF EXISTS django_admin_log CASCADE;
DROP TABLE IF EXISTS auth_user_user_permissions CASCADE;
DROP TABLE IF EXISTS auth_user_groups CASCADE;
DROP TABLE IF EXISTS auth_group_permissions CASCADE;
DROP TABLE IF EXISTS auth_permission CASCADE;
DROP TABLE IF EXISTS auth_group CASCADE;
DROP TABLE IF EXISTS auth_user CASCADE;
DROP TABLE IF EXISTS django_session CASCADE;
DROP TABLE IF EXISTS django_content_type CASCADE;

-- Dọn lịch sử migration của các app đã gỡ bỏ
DELETE FROM django_migrations WHERE app IN ('admin', 'auth', 'contenttypes', 'sessions');

-- ==============================================================================
-- 2. CẤU TRÚC 3 BẢNG NGHIỆP VỤ DUY NHẤT CỦA HỆ THỐNG
-- (Django tự động quản lý qua migrations: `python manage.py migrate`)
-- ==============================================================================

-- BẢNG 1: Danh sách Xã/Phường và Ranh giới GeoJSON (168 phường/xã TP.HCM)
-- gee_app_ward
--   - id: BIGSERIAL PRIMARY KEY
--   - ma_xa: VARCHAR(50) UNIQUE
--   - ten_xa: VARCHAR(255)
--   - geometry: JSONB

-- BẢNG 2: Quản lý Yêu cầu & Lịch sử Trích xuất ảnh Vệ tinh GEE
-- gee_app_geedatarequest
--   - id: BIGSERIAL PRIMARY KEY
--   - ward_id: BIGINT REFERENCES gee_app_ward(id)
--   - dataset: VARCHAR(100)
--   - start_date: DATE
--   - end_date: DATE
--   - requested_at: TIMESTAMP WITH TIME ZONE
--   - task_id: VARCHAR(100)
--   - drive_file_id: VARCHAR(100)
--   - download_url: VARCHAR(1000)
--   - csv_download_url: VARCHAR(1000)
--   - status: VARCHAR(20)
--   - ndvi_mean, ndwi_mean, ndbi_mean, lst_mean, dem_mean: DOUBLE PRECISION

-- BẢNG 3: Chuỗi Thời Gian Chỉ Số Phục Vụ Phân Tích & Vẽ Biểu Đồ
-- gee_app_observationdata
--   - id: BIGSERIAL PRIMARY KEY
--   - request_ref_id: BIGINT REFERENCES gee_app_geedatarequest(id)
--   - ward_id: BIGINT REFERENCES gee_app_ward(id)
--   - index_code: VARCHAR(20) -- 'NDVI', 'NDWI', 'NDBI', 'LST', 'DEM', 'TVDI'
--   - observation_time: DATE
--   - value: DOUBLE PRECISION

-- ==============================================================================
-- 4. CÂU LỆNH KIỂM TRA 50.400 DÒNG DỮ LIỆU LỚN (BIG DATA) TRONG CSDL
-- (Hãy bôi đen và nhấn Run/Execute để kiểm tra số liệu thực tế)
-- ==============================================================================

-- 4.1. Xem tổng số dòng trong bảng quan trắc (Chính xác: 50.400 dòng)
SELECT COUNT(*) AS tong_so_ban_ghi FROM gee_app_observationdata;

-- 4.2. Thống kê số lượng bản ghi theo từng chỉ số (Mỗi chỉ số đúng 10.080 bản ghi)
SELECT index_code AS chi_so, COUNT(*) AS so_luong_ban_ghi
FROM gee_app_observationdata
GROUP BY index_code
ORDER BY chi_so;

-- 4.3. Thống kê theo năm quan sát (Chuỗi 10 năm từ 2017 đến 2026)
SELECT EXTRACT(YEAR FROM observation_time) AS nam_quan_trac, COUNT(*) AS so_dong
FROM gee_app_observationdata
GROUP BY nam_quan_trac
ORDER BY nam_quan_trac;

-- 4.4. Xem 20 dòng số liệu viễn thám thực tế của các xã/phường
SELECT o.id, w.ten_xa, o.index_code, o.observation_time, o.value
FROM gee_app_observationdata o
JOIN gee_app_ward w ON o.ward_id = w.id
ORDER BY o.id
LIMIT 20;
