# Tiến độ thực hiện dự án GEE App

Dựa trên các yêu cầu ban đầu (`yeu_cau.md`), dưới đây là tiến trình và những phần việc đã được thực hiện:

## 1. Thiết lập & Cấu hình Project
- Khởi tạo ứng dụng Django `gee_app`.
- Thiết lập kết nối cơ sở dữ liệu (PostgreSQL/Supabase) để lưu trữ thông tin (thông qua `models.py`).

## 2. Xây dựng Cấu trúc Dữ liệu (Database Models)
- **Model `Ward`**: Lưu trữ thông tin địa giới Xã/Phường (mã xã, tên xã, và hình học `geometry` dạng GeoJSON) để cố định các khu vực có thể truy vấn.
- **Model `GEEDataRequest`**: Lưu trữ lịch sử tải dữ liệu của người dùng, bao gồm: khu vực, loại dữ liệu (`Landsat 8 TOA`, `Sentinel-2 SR`), thời gian (từ ngày - đến ngày), `Task ID` của GEE, đường dẫn tải từ Google Drive và trạng thái xử lý (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`, `DELETED`).

## 3. Xây dựng Xử lý logic & API (Views & Utils)
- **Giao diện chính (`home_view`)**: 
  - Cho phép người dùng nhập/chọn tên Xã/Phường, khoảng thời gian và loại dữ liệu cần tải.
  - Xử lý gộp nhiều Xã/Phường lại với nhau (gộp geometry) nếu người dùng chọn nhiều khu vực.
  - Gọi GEE API (`start_drive_export`) để tạo một tác vụ (Task) export dữ liệu vệ tinh trực tiếp sang Google Drive theo dạng file.
- **Trang lịch sử (`history_view`)**: 
  - Cập nhật trạng thái tự động (`check_task_and_get_drive_link`) của các tác vụ đang chạy (`PROCESSING`). 
  - Nếu hoàn tất, sẽ lấy `link` tải từ Google Drive cung cấp cho người dùng download về dễ dàng (mà không cần phải code trên GEE).
- **Chức năng giải phóng dung lượng (`delete_file_view`)**:
  - Hỗ trợ xóa các file hình ảnh kích thước lớn đã tải xuống khỏi Google Drive để tối ưu dung lượng cá nhân sau khi hoàn tất.

## 4. Xây dựng Routes (URLs)
- Định tuyến các URL `/` (Trang chủ), `/history/` (Lịch sử tải) và `/delete/<id>/` (Xóa file Drive).

## 5. Cải thiện Giao diện & Tính năng (Đã hoàn thành)
- **Tailwind CSS**: Đã cấu hình và sử dụng Tailwind CSS nội bộ (không qua CDN), tối ưu hóa trải nghiệm UI/UX trên cả PC và Mobile cho các trang `home` và `history`.
- **Đề xuất Shapefile**: Đã bổ sung tính năng gợi ý tải dữ liệu Shapefile_Geodatabase (ranh giới hành chính). Khi tải dữ liệu ảnh vệ tinh xong, người dùng có thể nhấp vào link chuyển hướng tải thư mục Shapefile trên Google Drive.
- **Seed dữ liệu CSDL**: Đã tạo Management Command `seed_wards.py` và import thành công danh sách các Phường/Xã khu vực TP. Hồ Chí Minh (loại bỏ Côn Đảo).

## 6. Tối ưu hóa Hiệu suất Máy chủ (Render & Supabase)
Để đáp ứng cho cấu trúc máy chủ Free Tier, hệ thống đã được tối ưu các nút thắt cổ chai (bottleneck):
- **PostgreSQL Connection Pooling**: Bật tính năng tái sử dụng kết nối (`CONN_MAX_AGE = 600`) để không làm sập Database Supabase khi có nhiều truy vấn liên tục.
- **Gunicorn Threading**: Định cấu hình lại lệnh khởi chạy Web Server (Render) bằng `--threads 4 --worker-class gthread` để giúp server xử lý được nhiều tiến trình đồng thời thay vì bị treo khi một request đang tải dữ liệu chậm. Kèm theo `--max-requests 1000` để chống phình RAM (Memory Leak).
- **Offload Băng thông**: File Shapefile khổng lồ đã được tách rời sang Google Drive nhằm giảm thiểu tối đa gánh nặng bộ nhớ và mạng cho máy chủ Render.
