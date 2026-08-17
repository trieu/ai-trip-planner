import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from markdownify import markdownify
import warnings
import re

# Bỏ qua các cảnh báo XML không cần thiết
warnings.filterwarnings('ignore')

def clean_filename(name):
    """Hàm phụ trợ: Làm sạch tên file để tránh các ký tự đặc biệt gây lỗi trên hệ điều hành"""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip().replace(" ", "_")

def epub_to_markdown_structure(epub_path):
    """
    Hàm xử lý chính: Đọc EPUB, tạo thư mục, trích xuất hình ảnh và lưu từng chương thành file MD.
    """
    print(f"🚀 Bắt đầu xử lý: {epub_path}")
    
    # 1. Khởi tạo cấu trúc thư mục
    # Lấy tên file gốc (không chứa đuôi .epub) làm tên thư mục chính
    base_name = os.path.splitext(os.path.basename(epub_path))[0]
    output_dir = base_name
    images_dir = os.path.join(output_dir, "images")
    
    # Tạo thư mục chính và thư mục con images (nếu chưa có)
    os.makedirs(images_dir, exist_ok=True)
    
    # Đọc file EPUB
    book = epub.read_epub(epub_path)
    
    # 2. Trích xuất toàn bộ hình ảnh
    print("📸 Đang trích xuất hình ảnh...")
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        # Lấy tên gốc của ảnh
        img_name = os.path.basename(item.get_name())
        img_path = os.path.join(images_dir, img_name)
        
        # Lưu file ảnh xuống ổ cứng
        with open(img_path, 'wb') as f:
            f.write(item.get_content())
            
    # 3. Đọc Mục lục (TOC) và Trích xuất Nội dung
    print("📖 Đang chuyển đổi các chương sang Markdown...")
    # 'spine' trong EPUB lưu trữ thứ tự đọc chính xác (Reading Order) của các chương
    spine = book.spine
    chapter_index = 1
    
    for item_id, _ in spine:
        item = book.get_item_with_id(item_id)
        
        # Chỉ xử lý nếu item là một trang tài liệu HTML/XHTML
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            html_content = item.get_content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # --- XỬ LÝ HÌNH ẢNH TRONG HTML ---
            # Tìm tất cả thẻ <img> và cập nhật lại đường dẫn để trỏ tới thư mục 'images/'
            for img in soup.find_all('img'):
                if img.get('src'):
                    old_src = img['src']
                    new_src = f"images/{os.path.basename(old_src)}" # Cấu trúc: images/ten_anh.jpg
                    img['src'] = new_src
                    
            # --- XÁC ĐỊNH TÊN FILE CHO CHƯƠNG ---
            # Thử lấy thẻ <title> hoặc <h1> làm tên file
            title_tag = soup.find('title') or soup.find('h1')
            if title_tag and title_tag.text.strip():
                chapter_title = clean_filename(title_tag.text.strip())
            else:
                chapter_title = f"Chapter"
                
            # Đánh số thứ tự (01, 02,...) để giữ đúng flow khi đọc
            file_name = f"{chapter_index:02d}_{chapter_title}.md"
            file_path = os.path.join(output_dir, file_name)
            
            # --- CONVERT SANG MARKDOWN ---
            # Sử dụng markdownify với chuẩn ATX (dùng dấu # cho Heading thay vì gạch chân)
            md_content = markdownify(str(soup), heading_style="ATX")
            
            # Xóa bớt các khoảng trắng thừa ở đầu/cuối và lưu file
            if md_content.strip():
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(md_content.strip())
                chapter_index += 1

    print(f"✅ Hoàn tất! Toàn bộ nội dung đã được lưu tại thư mục: ./{output_dir}/")

# ==========================================
# THỰC THI CHƯƠNG TRÌNH
# ==========================================
if __name__ == '__main__':
    # Đặt file EPUB của bạn cùng thư mục với script này
    target_epub = '/home/thomas/Documents/Brand Management Co-Creating Meaningful Brands.epub' 
    
    try:
        epub_to_markdown_structure(target_epub)
    except Exception as e:
        print(f"❌ Có lỗi xảy ra: {e}")