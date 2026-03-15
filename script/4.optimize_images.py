# --- START OF FILE script/4.optimize_images.py ---
import os
import shutil
from PIL import Image

# --- 설정 ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE_DIR, "app", "static", "img")
BACKUP_DIR = os.path.join(IMG_DIR, "original_backup")

# 최적화 설정
MAX_WIDTH = 800        # 이미지의 최대 가로 길이 (픽셀)
JPEG_QUALITY = 85      # JPEG 저장 품질 (0~100, 85가 웹 최적화에 가장 좋음)

def optimize_images():
    print(f"🖼️ Starting Image Optimization in: {IMG_DIR}")
    
    # 백업 폴더가 없으면 생성
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"   📂 Created backup folder: {BACKUP_DIR}")

    # 지원하는 이미지 확장자
    supported_formats = ('.png', '.jpg', '.jpeg', '.webp')
    processed_count = 0

    for filename in os.listdir(IMG_DIR):
        file_path = os.path.join(IMG_DIR, filename)

        # 폴더이거나 지원하지 않는 파일, 이미 변환된 파일은 스킵
        if os.path.isdir(file_path):
            continue
        
        lower_filename = filename.lower()
        if not lower_filename.endswith(supported_formats):
            continue

        try:
            with Image.open(file_path) as img:
                # 1. RGBA(투명 배경이 있는 PNG 등) 이미지를 RGB로 변환 (JPEG는 투명을 지원하지 않음)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # 2. 이미지 리사이즈 (가로가 MAX_WIDTH보다 크면 비율에 맞게 줄임)
                if img.width > MAX_WIDTH:
                    ratio = MAX_WIDTH / img.width
                    new_height = int(img.height * ratio)
                    # Resampling.LANCZOS는 안티앨리어싱 품질이 가장 좋은 옵션입니다.
                    img = img.resize((MAX_WIDTH, new_height), Image.Resampling.LANCZOS)
                
                # 3. 새로운 파일명 설정 (기존 확장자를 .jpeg로 변경)
                base_name = os.path.splitext(filename)[0]
                new_filename = f"{base_name}.jpeg"
                new_file_path = os.path.join(IMG_DIR, new_filename)

                # 4. 백업: 원본 파일을 백업 폴더로 이동
                backup_path = os.path.join(BACKUP_DIR, filename)
                shutil.move(file_path, backup_path)

                # 5. 최적화된 JPEG로 저장
                img.save(new_file_path, "JPEG", optimize=True, quality=JPEG_QUALITY)
                
                # 파일 용량 비교 출력 (KB)
                old_size = os.path.getsize(backup_path) / 1024
                new_size = os.path.getsize(new_file_path) / 1024
                print(f"   ✅ Optimized: {filename} -> {new_filename} ({old_size:.1f}KB -> {new_size:.1f}KB)")
                
                processed_count += 1

        except Exception as e:
            print(f"   ❌ Error processing {filename}: {e}")

    print(f"\n🎉 Done! Successfully optimized {processed_count} images.")
    print(f"   (Originals are safely stored in: app/static/img/original_backup/)")

if __name__ == "__main__":
    optimize_images()