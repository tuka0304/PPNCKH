Dựa trên cấu trúc thư mục và tên các file hiện có trong repository **PPNCKH** trên màn hình của bạn, dự án này là một **Hệ thống WebGIS phục vụ Nghiên cứu Khoa học (Phương pháp Nghiên cứu Khoa học)**, sử dụng **Django (Python)** kết hợp với **Google Earth Engine (GEE)** để phân tích chuỗi thời gian các chỉ số viễn thám như **Nhiệt độ bề mặt (LST), NDVI và TVDI** tại khu vực **TP. Hồ Chí Minh (HCMC)**, và được cấu hình để triển khai trên **Render**.

*(Lưu ý: Do hiện tại chỉ có thể quan sát danh sách tên file ở thanh bên trái mà chưa xem được nội dung chi tiết bên trong từng file code, bản `README.md` dưới đây được thiết kế chuẩn xác theo các thành phần hiện có của dự án. Bạn có thể copy trực tiếp vào khung soạn thảo và tinh chỉnh lại các thông số cụ thể nếu cần).*

```markdown
# 🌍 Hệ thống Phân tích & Giám sát Viễn thám (LST - NDVI - TVDI) Khu vực TP.HCM

Dự án nghiên cứu khoa học (PPNCKH) ứng dụng công nghệ **Google Earth Engine (GEE)** và **Django Framework** nhằm thu thập, xử lý và trực quan hóa dữ liệu chuỗi thời gian (Time-series) các chỉ số viễn thám: **Nhiệt độ bề mặt (LST)**, **Chỉ số thực vật (NDVI)** và **Chỉ số khô hạn nhiệt độ - thực vật (TVDI)** tại khu vực Thành phố Hồ Chí Minh.

---

## ✨ Tính năng chính

* **Phân tích dữ liệu Google Earth Engine (GEE):** Tự động hóa quá trình thu thập và tính toán các chỉ số LST, NDVI, TVDI theo chuỗi thời gian cho khu vực TP.HCM (`generate_hcmc_timeseries.py`).
* **Xử lý dữ liệu không gian (GIS):** Hỗ trợ đọc, cắt và xử lý ranh giới hành chính từ định dạng Shapefile (`process_shapefile.py`).
* **Trực quan hóa bản đồ & Thang màu chuẩn:** Hiển thị các lớp bản đồ phân bố nhiệt độ, thảm thực vật và mức độ khô hạn theo thang màu tiêu chuẩn (`Thang màu Nhiệt độ-NDVI-TVDI.pdf`).
* **Quản trị & Sao lưu Cơ sở dữ liệu:** Tích hợp các công cụ tự động sao lưu (`backup_remote_db.py`) và phục hồi (`restore_remote_db.py`) cơ sở dữ liệu từ xa.
* **Trích xuất báo cáo:** Hỗ trợ trích xuất dữ liệu và nội dung phục vụ báo cáo từ các định dạng văn bản (`extract_docx.py`).

---

## 🛠️ Công nghệ sử dụng

* **Backend:** Python, Django (`manage.py`, `gee_project`, `gee_app`)
* **Viễn thám & GIS:** Google Earth Engine API, Geopandas / Shapely
* **Frontend / Thư viện bổ trợ:** HTML/CSS/JS, Node.js packages (`package.json`)
* **Cơ sở dữ liệu:** PostgreSQL / SQLite (`render_db.session.sql`)
* **Triển khai (Deployment):** Render (`render.yaml`, `build.sh`)

---

## 📂 Cấu trúc thư mục

```text
PPNCKH/
├── gee_app/                        # Ứng dụng Django chính xử lý logic hiển thị và API GEE
├── gee_project/                    # Cấu hình cốt lõi của dự án Django (settings, urls, wsgi)
├── generate_hcmc_timeseries.py     # Script tạo dữ liệu chuỗi thời gian tại TP.HCM
├── process_shapefile.py            # Script xử lý dữ liệu bản đồ Shapefile
├── backup_remote_db.py             # Script sao lưu cơ sở dữ liệu từ xa
├── restore_remote_db.py            # Script khôi phục cơ sở dữ liệu từ xa
├── extract_docx.py                 # Công cụ trích xuất dữ liệu từ file Word (.docx)
├── Thang màu Nhiệt độ-NDVI-TVDI.pdf # Tài liệu quy chuẩn thang màu hiển thị bản đồ
├── tien_trinh.md                   # Tài liệu theo dõi tiến trình thực hiện dự án
├── yeu_cau.md                      # Tài liệu đặc tả yêu cầu của hệ thống
├── manage.py                       # Công cụ dòng lệnh quản lý dự án Django
├── requirements.txt                # Danh sách các thư viện Python cần thiết
├── package.json                    # Danh sách các gói phụ thuộc Frontend/Node
├── build.sh                        # Script cài đặt và build hệ thống trên môi trường production
└── render.yaml                     # File cấu hình triển khai tự động trên Render

```

---

## 🚀 Hướng dẫn cài đặt và Chạy dự án (Local)

### 1. Yêu cầu hệ thống

* Python 3.9+ (xem chi tiết phiên bản tại `.python-version`)
* Tài khoản đã đăng ký quyền truy cập **Google Earth Engine**
* Node.js & npm (nếu cần biên dịch tài nguyên frontend)

### 2. Cài đặt môi trường

**Bước 1: Clone repository về máy**

```bash
git clone [https://github.com/tuka0304/PPNCKH.git](https://github.com/tuka0304/PPNCKH.git)
cd PPNCKH

```

**Bước 2: Tạo và kích hoạt môi trường ảo (Virtual Environment)**

```bash
python -m venv venv
# Trên Windows:
venv\Scripts\activate
# Trên macOS/Linux:
source venv/bin/activate

```

**Bước 3: Cài đặt các thư viện cần thiết**

```bash
pip install -r requirements.txt
npm install

```

**Bước 4: Xác thực Google Earth Engine**

```bash
earthengine authenticate

```

**Bước 5: Thiết lập cơ sở dữ liệu và chạy Server**

```bash
python manage.py migrate
python manage.py runserver

```

Truy cập ứng dụng tại địa chỉ: `http://127.0.0.1:8000/`

---

## ☁️ Triển khai (Deployment)

Dự án đã được cấu hình sẵn để triển khai đám mây trên nền tảng **Render** thông qua file `render.yaml` và script `build.sh`.

* Để sao lưu dữ liệu từ database trên Render về máy:
```bash
python backup_remote_db.py

```


* Để khôi phục dữ liệu lên database từ xa:
```bash
python restore_remote_db.py

```



---

## 📄 Tài liệu tham khảo nội bộ

* Xem chi tiết yêu cầu đề tài tại: yeu_cau.md
* Theo dõi tiến độ cập nhật tại: tien_trinh.md

```

---

Nếu bạn muốn bổ sung thông tin chi tiết hơn (như tên thành viên nhóm, giảng viên hướng dẫn, hoặc chi tiết thuật toán trong `yeu_cau.md`), bạn có thể dán nội dung file `yeu_cau.md` hoặc `tien_trinh.md` vào đây để mình cập nhật lại file README cho sát thực tế nhất!

```
