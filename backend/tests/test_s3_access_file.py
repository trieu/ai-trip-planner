
# Test S3 Access File



# ------------------------------------------------------------------------
ACCESS_KEY='32d23ffadef5de5ff3f5'      # Thay bằng Access Key của bạn
SECRET_KEY='RRjsK+jInmbiGLlvsUQeA8sz7DEHCWVzMnCo9sFM'  # Thay bằng Secret Key của bạn
# ------------------------------------------------------------------------

import boto3
from botocore.client import Config


# Khởi tạo S3 Client
s3_client = boto3.client(
    's3',
    endpoint_url='https://s3-north1.viettelidc.com.vn',
    aws_access_key_id=ACCESS_KEY,      
    aws_secret_access_key=SECRET_KEY,  
    config=Config(
        signature_version='s3v4',
        s3={'addressing_style': 'path'}  # Bắt buộc path-style để tránh lỗi chữ ký
    ),
    region_name='north'
)

# --- TÍNH NĂNG MỚI: CẤP QUYỀN PUBLIC CHO FILE ---
def make_file_public(bucket_name, object_name):
    """
    Chuyển đổi quyền của file thành Public Read.
    Lưu ý: Tài khoản của bạn cần có quyền s3:PutObjectAcl.
    """
    try:
        s3_client.put_object_acl(
            ACL='public-read',
            Bucket=bucket_name,
            Key=object_name
        )
        print(f"[Thành công] Đã cấp quyền Public Read cho file: {object_name}")
        return True
    except Exception as e:
        print(f"[Thất bại] Lỗi khi cấp quyền Public: {e}")
        return False

# --- OPTION 1: Pre-signed URL (Mặc định Viettel) ---
def get_presigned_url(bucket_name, object_name, expiration=3600):
    try:
        return s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': bucket_name, 'Key': object_name},
            ExpiresIn=expiration
        )
    except Exception as e:
        print(f"Lỗi tạo Pre-signed URL: {e}")
        return None

# --- OPTION 2: Direct Public URL (Mặc định Viettel) ---
def get_direct_public_url(bucket_name, object_name):
    return f"https://s3-north1.viettelidc.com.vn/{bucket_name}/{object_name}"

# --- OPTION 3A: Custom Domain Public URL (Tĩnh) ---
def get_custom_domain_public_url(custom_domain, object_name):
    """
    Tạo link Public sử dụng tên miền riêng.
    Yêu cầu: Đã trỏ CNAME tên miền về Viettel S3 & File đã được mở Public.
    """
    return f"https://{custom_domain}/{object_name}"

# --- OPTION 3B: Custom Domain Pre-signed URL (Bảo mật) ---
def get_custom_domain_presigned_url(bucket_name, custom_domain, object_name, expiration=3600):
    """
    Tạo link có chữ ký nhưng thay thế endpoint gốc bằng tên miền riêng.
    (Chỉ nên dùng nếu cấu hình reverse proxy ở phía tên miền riêng để dịch lại URL)
    """
    original_url = get_presigned_url(bucket_name, object_name, expiration)
    if original_url:
        old_base = f"https://s3-north1.viettelidc.com.vn/{bucket_name}"
        new_base = f"https://{custom_domain}"
        return original_url.replace(old_base, new_base)
    return None


# ================= SỬ DỤNG =================
if __name__ == "__main__":
    bucket = 'files.axisgroup.vn'
    custom_domain = 'files.axisgroup.vn' 
    file_key = 'sample.pdf'

    # 1. Bật quyền public cho file trước khi gọi link Public tĩnh
    print("--- ĐANG CẤP QUYỀN PUBLIC CHO FILE ---")
    make_file_public(bucket, file_key)
    print("-" * 50)

    # 2. In ra các định dạng URL
    print("1. Pre-signed URL (Gốc Viettel):")
    print(get_presigned_url(bucket, file_key))
    print("-" * 50)

    print("2. Direct Public URL (Gốc Viettel):")
    print(get_direct_public_url(bucket, file_key))
    print("-" * 50)

    print("3A. Custom Domain Public URL (Sử dụng URL này vì file đã được Public):")
    print(get_custom_domain_public_url(custom_domain, file_key))
    print("-" * 50)

    # Option 3B thường gây lỗi SignatureMismatch nếu truy cập trực tiếp bằng trình duyệt mà không qua Nginx/Proxy
    print("3B. Custom Domain Pre-signed URL (Link tên miền riêng kèm bảo mật):")
    print(get_custom_domain_presigned_url(bucket, custom_domain, file_key))