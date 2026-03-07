import sys
import os
import json
import frontmatter

# --- 설정 ---
# 경로 설정 (상위 폴더 인식)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(BASE_DIR, "app", "content")
DATA_DIR = os.path.join(BASE_DIR, "data")
INDEX_PATH = os.path.join(DATA_DIR, "search_index.json")

def update_search_index():
    """
    app/content 폴더의 모든 마크다운 파일을 스캔하여
    다국어 정보를 포함한 통합 검색 인덱스(JSON)를 생성합니다.
    """
    print("🚀 Building multi-language search index...")
    index_data = []
    
    # content 폴더가 없으면 생성
    if not os.path.exists(CONTENT_DIR):
        os.makedirs(CONTENT_DIR)
        print(f"⚠️ Content directory not found. Created: {CONTENT_DIR}")
        return

    # data 폴더가 없으면 생성
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    files_found = 0
    # content 폴더의 모든 파일을 순회
    for filename in os.listdir(CONTENT_DIR):
        if filename.endswith(".md"):
            files_found += 1
            try:
                # --- 언어 및 기본 슬러그 판별 ---
                lang = "en" # 기본값
                base_slug = ""
                
                if filename.endswith("_ko.md"):
                    lang = "ko"
                    base_slug = filename.replace("_ko.md", "")
                elif filename.endswith("_ja.md"):
                    lang = "ja"
                    base_slug = filename.replace("_ja.md", "")
                else:
                    # _ko, _ja가 없는 경우 기본 영어 파일로 간주
                    lang = "en"
                    base_slug = filename.replace(".md", "")
                
                # 파일 읽기 및 메타데이터 파싱
                file_path = os.path.join(CONTENT_DIR, filename)
                with open(file_path, "r", encoding="utf-8") as f:
                    post = frontmatter.load(f)
                    
                # 인덱스 데이터 구성
                index_data.append({
                    "lang": lang,        # 언어 코드 (en, ko, ja)
                    "slug": base_slug,   # 언어 접미사가 제거된 공통 슬러그 (URL 링크용)
                    "file": filename,    # 실제 파일명 (디버깅용)
                    "name": post.metadata.get("title", "Unknown Title"),
                    "sneaker": post.metadata.get("sneaker_model", "Unknown Sneaker"),
                    "era": post.metadata.get("era", "History"),
                    # 이미지는 언어 상관없이 공통된 이미지를 사용한다고 가정 (확장자는 jpg로 통일 권장)
                    # 실제 존재하는지 여부는 main.py에서 체크하므로 여기서는 경로만 지정
                    "image": f"/static/img/{base_slug}.jpeg" 
                })
                print(f"   Generation index entry for: {filename} ({lang})")

            except Exception as e:
                print(f"⚠️ Error parsing {filename}: {e}")
    
    if files_found == 0:
         print("⚠️ No markdown files found in app/content/.")

    # JSON 파일로 저장
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Search index updated successfully at: {INDEX_PATH}")
    print(f"📊 Total indexed items: {len(index_data)}")

if __name__ == "__main__":
    # 이 스크립트를 직접 실행할 때만 인덱스 업데이트 수행
    update_search_index()