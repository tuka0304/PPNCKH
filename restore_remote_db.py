"""
Script khôi phục (Restore) dữ liệu từ file backup lên CSDL Render PostgreSQL mới.
Sử dụng:
    python restore_remote_db.py [NEW_DATABASE_URL] [BACKUP_FILE]

Mặc định đọc file 'backup_render_db.json' (hoặc 'backup_gee_app.json').
"""

import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

def main():
    if len(sys.argv) < 2:
        print("=" * 60)
        print("  CÔNG CỤ PHỤC HỒI DỮ LIỆU LÊN RENDER POSTGRESQL MỚI")
        print("=" * 60)
        print("Cú pháp sử dụng:")
        print("    python restore_remote_db.py <NEW_DATABASE_URL> [FILE_BACKUP]")
        print("\nVí dụ:")
        print("    python restore_remote_db.py postgres://user:pass@dpg-xxx.render.com/dbname backup_render_db.json\n")
        sys.exit(1)

    db_url = sys.argv[1].strip()
    backup_file = sys.argv[2].strip() if len(sys.argv) > 2 else 'backup_render_db.json'

    if not os.path.exists(backup_file):
        if os.path.exists('backup_gee_app.json'):
            backup_file = 'backup_gee_app.json'
        else:
            print(f"Lỗi: Không tìm thấy file sao lưu '{backup_file}'.")
            sys.exit(1)

    os.environ['DATABASE_URL'] = db_url
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gee_project.settings')

    import django
    django.setup()

    from django.core.management import call_command
    from gee_app.models import Ward, GEEDataRequest, ObservationData

    print(f"\n[1/3] Đang chạy migrations trên CSDL mới...")
    call_command('migrate', interactive=False)

    print(f"\n[2/3] Đang nạp dữ liệu từ '{backup_file}' lên CSDL mới...")
    call_command('loaddata', backup_file)

    print(f"\n[3/3] Kiểm tra dữ liệu trên CSDL mới:")
    print(f"  + Số lượng Xã/Phường: {Ward.objects.count()}")
    print(f"  + Số lượng Lịch sử Yêu cầu: {GEEDataRequest.objects.count()}")
    print(f"  + Số lượng Bản ghi Chuỗi thời gian: {ObservationData.objects.count()}")
    print("\nKhôi phục dữ liệu lên CSDL Render mới thành công rực rỡ!\n")

if __name__ == '__main__':
    main()
