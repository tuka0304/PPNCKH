Hãy viết chương trình website quản lý dữ liệu lớn về GEE bằng cách API đến GEE và lưu vào CSDL PostgreSQL.
Trong đó có 2 chức năng:
1. Lấy dữ liệu từ GEE và lưu vào CSDL
2. Truy vấn dữ liệu từ CSDL
3. Cố định khu vực TP Hồ Chí Minh (không tính côn đảo), người dùng có thể chọn khu vực theo địa phận xã phường (sau sáp nhập), theo thời gian chọn loại dữ liệu chọn size rồi tải về không cần viết script trực tiếp trên GEE giúp người không am hiểu code vẫn có thể tải dữ liệu
4. Giao diện thân thiện dễ dùng sử dụng tailwind css có thể xem web trên mobile hoặc PC
5. Tích hợp toàn bộ thư viện cần thiết vào dự án không dùng CDN và phù hợp để deploy render
6. Dùng python kết nối với GEE và CSDL với framework Django và kết nối với Supabase
7. Khi người dùng tải ảnh dữ liệu về sẽ đề xuất hỏi người dùng có nhu cầu tải  Shapefile_Geodatabase.zip hay không