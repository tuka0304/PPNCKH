-- Kích hoạt extension PostGIS cho không gian
CREATE EXTENSION IF NOT EXISTS postgis;

-- ==============================================================================
-- 1. DANH MỤC CƠ BẢN (META DATA)
-- ==============================================================================

-- Bảng lưu trữ 3 loại chỉ số (VD: NDVI, NDWI, NDBI/LST)
CREATE TABLE IF NOT EXISTS index_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100),
    description TEXT
);

-- Bảng lưu trữ nguồn gốc dữ liệu (Phân biệt GEE và kết quả mô hình/giả lập)
CREATE TABLE IF NOT EXISTS data_origins (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE, -- 'GEE_CURRENT', 'MODEL_FORECAST', 'SIMULATION'
    name VARCHAR(100),
    description TEXT
);

-- ==============================================================================
-- 2. DỮ LIỆU KHÔNG GIAN VÀ ĐỊA GIỚI (Dùng cho thống kê, phân tích)
-- ==============================================================================

-- Bảng lưu trữ các vùng quan tâm (ROI), ranh giới hành chính
CREATE TABLE IF NOT EXISTS spatial_regions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    region_level VARCHAR(50), -- Province, District, Ward, Custom
    geom GEOMETRY(MultiPolygon, 4326) -- Lưu trữ đa giác ranh giới
);
-- Index không gian cho vùng
CREATE INDEX idx_regions_geom ON spatial_regions USING GIST (geom);

-- ==============================================================================
-- 3. DỮ LIỆU BIG DATA (KIẾN TRÚC PARTITIONING)
-- ==============================================================================
-- Bảng chính lưu trữ dữ liệu raster/vector đã trích xuất từ GEE hoặc Mô hình.
-- Sử dụng kỹ thuật PARTITION BY RANGE (theo thời gian) để xử lý Big Data.

CREATE TABLE IF NOT EXISTS observation_data (
    id BIGSERIAL,
    region_id INTEGER REFERENCES spatial_regions(id),
    index_type_id INTEGER REFERENCES index_types(id),
    origin_id INTEGER REFERENCES data_origins(id),
    observation_time TIMESTAMP NOT NULL,
    value DOUBLE PRECISION,
    geom GEOMETRY(Geometry, 4326), -- Có thể là Point (pixel) hoặc Polygon
    metadata JSONB, -- Lưu trữ các tham số bổ sung linh hoạt (cloud_cover, model_params...)
    PRIMARY KEY (observation_time, id)
) PARTITION BY RANGE (observation_time);

-- Tạo các partition theo năm (có thể chia nhỏ theo tháng nếu dữ liệu quá lớn)
CREATE TABLE observation_data_2024 PARTITION OF observation_data
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');

CREATE TABLE observation_data_2025 PARTITION OF observation_data
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE observation_data_2026 PARTITION OF observation_data
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

-- Index không gian và thời gian cho Big Data để truy vấn cực nhanh
CREATE INDEX idx_obs_data_geom ON observation_data USING GIST (geom);
CREATE INDEX idx_obs_data_time ON observation_data (observation_time);
CREATE INDEX idx_obs_data_lookup ON observation_data (index_type_id, origin_id, region_id);
CREATE INDEX idx_obs_data_meta ON observation_data USING GIN (metadata);

-- ==============================================================================
-- 4. DỮ LIỆU THỐNG KÊ, PHÂN TÍCH (OLAP / DATAMART)
-- ==============================================================================
-- Bảng này lưu trữ dữ liệu đã được pre-calculate (min, max, avg) để phục vụ
-- trực quan hóa biểu đồ nhanh chóng mà không cần scan lại bảng Big Data.

CREATE TABLE IF NOT EXISTS aggregated_statistics (
    id BIGSERIAL PRIMARY KEY,
    region_id INTEGER REFERENCES spatial_regions(id),
    index_type_id INTEGER REFERENCES index_types(id),
    origin_id INTEGER REFERENCES data_origins(id),
    period_type VARCHAR(20), -- 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY'
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    min_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    avg_value DOUBLE PRECISION,
    std_dev DOUBLE PRECISION
);
CREATE INDEX idx_agg_stats_lookup ON aggregated_statistics (region_id, index_type_id, origin_id, start_time);
