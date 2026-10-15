"""
Script sao lưu (Backup) CSDL từ Render PostgreSQL về máy cục bộ.
Sử dụng:
    python backup_remote_db.py [DATABASE_URL]

Nếu không truyền DATABASE_URL, script sẽ hỏi nhập URL (lấy từ mục 'External Database URL' trên Render Dashboard).
Dữ liệu sẽ được lưu vào file 'backup_render_db.json' (chuẩn UTF-8) và tùy chọn nạp vào db.sqlite3 cục bộ.
"""

import os
import sys
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def main():
    db_url = None
    if len(sys.argv) > 1:
        db_url = sys.argv[1].strip()
    else:
        print("=" * 60)
        print("  CÔNG CỤ SAO LƯU DỮ LIỆU TỪ RENDER POSTGRESQL VỀ MÁY")
        print("=" * 60)
        print("Vào Render Dashboard -> Chọn PostgreSQL Database của bạn")
        print("-> Copy đường link tại mục 'External Database URL'")
        print("   (Có dạng: postgres://user:password@dpg-...render.com/dbname)\n")
        try:
            db_url = input("Dán External Database URL vào đây (hoặc Enter để dùng DB hiện tại): ").strip()
        except EOFError:
            pass

    if db_url:
        # Tạm thời gán DATABASE_URL môi trường để Django kết nối thẳng lên Render
        os.environ['DATABASE_URL'] = db_url

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gee_project.settings')
    
    import django
    django.setup()
    
    from django.core.management import call_command
    from io import StringIO
    from gee_app.models import Ward, GEEDataRequest, ObservationData

    print(f"\n[1/3] Đang kết nối CSDL...")
    ward_count = Ward.objects.count()
    req_count = GEEDataRequest.objects.count()
    obs_count = ObservationData.objects.count()

    print(f"  + Số lượng Xã/Phường: {ward_count}")
    print(f"  + Số lượng Lịch sử Yêu cầu: {req_count}")
    print(f"  + Số lượng Bản ghi Chuỗi thời gian: {obs_count}")

    output_file = 'backup_render_db.json'
    print(f"\n[2/3] Đang trích xuất dữ liệu sang '{output_file}'...")
    buf = StringIO()
    call_command('dumpdata', 'gee_app', stdout=buf)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(buf.getvalue())

    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"  -> Đã lưu thành công file '{output_file}' ({file_size_mb:.2f} MB)")

    print("\n[3/3] Hoàn tất sao lưu an toàn! Dữ liệu của bạn đã được bảo toàn về máy tính.")
    print("Khi tạo DB mới trên Render, bạn chỉ cần dùng lệnh:")
    print("    python restore_remote_db.py <NEW_DATABASE_URL>\n")

if __name__ == '__main__':
    main()
