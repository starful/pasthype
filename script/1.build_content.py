# --- START OF FILE script/build_content.py ---
import sys
import os
import pandas as pd
import frontmatter
import google.generativeai as genai
from dotenv import load_dotenv
import time
import re
import json
from datetime import datetime

# 경로 설정 (상위 폴더 인식)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import CSV_PATH, CONTENT_DIR, DATA_DIR, INDEX_PATH, CATEGORIES

# AI 설정
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# 모델 설정: 요청에 따라 gemini-flash-latest 사용
MODEL = genai.GenerativeModel('gemini-flash-latest')

def slugify(text):
    """
    텍스트를 URL 친화적인 slug로 변환합니다.
    예: "Guan Yu (관우)" -> "guan-yu"
    """
    text = text.lower()
    # 괄호 안의 내용은 제거 (한글 이름 등)
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def generate_kicks_content():
    """CSV를 읽어 역사적 인물 x 스니커즈 매칭 대하드라마급 리포트 생성 (JSON 강제, 최대 4개 제한)"""
    if not os.path.exists(CSV_PATH):
        print("❌ CSV 파일이 없습니다.")
        return

    df = pd.read_csv(CSV_PATH)
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    print(f"🚀 총 {len(df)}명의 인물에 대한 심층 분석을 시작합니다 (English Mode, Max 4 new items, JSON Enforced)...")

    new_generated_count = 0
    max_to_generate = 4

    for _, row in df.iterrows():
        # 최대 생성 개수에 도달하면 루프 종료
        if new_generated_count >= max_to_generate:
            print(f"\n🛑 Limit reached: Created {max_to_generate} new articles for this run.")
            break

        name_raw = row['name']
        file_slug = slugify(name_raw)
        file_path = os.path.join(CONTENT_DIR, f"{file_slug}.md")

        # 이미 존재하면 스킵 (덮어쓰기 하려면 이 부분 주석 처리)
        if os.path.exists(file_path):
            print(f"   ⏭️  Skipped: {file_slug}.md (Already exists)")
            continue

        print(f"\n   👟 Generating deep dive for: {name_raw} (New item {new_generated_count + 1}/{max_to_generate}) ...")
        
        # --- AI 프롬프트 (JSON 응답 강제 및 마크다운 이스케이프 방지 구조) ---
        prompt = f"""
        Act as a professional fashion historian and sneaker columnist (like Highsnobiety or Hypebeast editor).
        
        Target Profile:
        - Name: {name_raw}
        - Era: {row['era']}
        - Role: {row['role']}
        - Traits: {row['keywords']}

        [Task]
        Match a specific sneaker model to this historical figure and write a VERY DETAILED, LONG-FORM article (approx. 1200-1500+ words).
        
        [Crucial Instruction]
        1. WRITE THE ENTIRE OUTPUT STRICTLY IN ENGLISH.
        2. YOU MUST RESPOND ONLY WITH A VALID JSON OBJECT. NO MARKDOWN FORMATTING OUTSIDE THE JSON.
        3. Do not use unescaped quotes or newlines inside the JSON strings. Use standard JSON formatting.

        [JSON Structure Required]
        {{
            "title": "A catchy title (e.g., The God of War in Lost & Found: Guan Yu's Eternal Flex)",
            "sneaker_model": "Full name of the sneaker",
            "sneaker_brand": "Brand",
            "era": "{row['era']}",
            "resell_price": "Estimated resell price (e.g., $500)",
            "image_prompt": "A highly detailed prompt for an AI image generator",
            "section_fit_check": "Detailed text for 'The Fit Check' section (No markdown headings inside here)",
            "section_why_this": "Detailed text for 'Why This Kicks?' section",
            "section_design": "Detailed text for 'Color & Design DNA' section",
            "section_styling": "Detailed text for 'OOTD Styling Guide' section",
            "section_reactions": "Detailed text for 'Imaginary Reactions' section"
        }}
        """
        
        try:
            # 긴 텍스트 생성을 위해 max_output_tokens 설정 추가
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=8192, 
                temperature=0.7,
                response_mime_type="application/json" # JSON 강제
            )
            
            response = MODEL.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            try:
                # [안전장치 추가] AI가 ```json 과 ``` 로 감싸서 보냈을 경우를 대비해 텍스트 정제
                raw_text = response.text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()
                
                data = json.loads(raw_text)
            except json.JSONDecodeError as e:
                print(f"   ❌ Error: AI did not return valid JSON for {name_raw}. Error: {e}")
                print(f"   [Raw AI Response]:\n{response.text[:200]}...") # 원인 파악을 위해 앞부분 출력
                continue

            # ========================================================
            # 데이터 정제 및 Frontmatter 파싱 강제화 (Python으로 조립)
            # ========================================================
            safe_title = str(data.get('title', name_raw)).replace('"', "'")
            safe_sneaker = str(data.get('sneaker_model', 'Unknown Sneaker')).replace('"', "'")
            safe_brand = str(data.get('sneaker_brand', 'Unknown Brand')).replace('"', "'")
            safe_era = str(data.get('era', 'History')).replace('"', "'")
            safe_price = str(data.get('resell_price', 'N/A')).replace('"', "'")
            safe_prompt = str(data.get('image_prompt', '')).replace('"', "'")
            
            # JSON에서 각각의 섹션을 가져와 마크다운 본문으로 결합합니다.
            content_body = f"""## 🕶️ The Fit Check
{data.get('section_fit_check', 'Content missing.')}

## 👟 Why This Kicks?
{data.get('section_why_this', 'Content missing.')}

## 🎨 Color & Design DNA
{data.get('section_design', 'Content missing.')}

## 👕 OOTD Styling Guide
{data.get('section_styling', 'Content missing.')}

## 💬 Imaginary Reactions
{data.get('section_reactions', 'Content missing.')}"""

            final_markdown = f"""---
title: "{safe_title}"
title_slug: "{file_slug}"
sneaker_model: "{safe_sneaker}"
sneaker_brand: "{safe_brand}"
era: "{safe_era}"
resell_price: "{safe_price}"
image_prompt: "{safe_prompt}"
---

{content_body}
"""
            # 파일 저장
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(final_markdown)
            
            print(f"   ✅ Created: {file_slug}.md (JSON parsed successfully, Length: {len(final_markdown)} chars)")
            
            # 새로 생성했을 때만 카운트 증가
            new_generated_count += 1
            time.sleep(5) 
            
        except Exception as e:
            print(f"   ❌ Error generating content for {name_raw}: {e}")
            time.sleep(10)

def update_search_index():
    """
    참고: 다국어 버전을 사용 중이시라면 이 함수 대신 
    새로 만드신 `script/build_index.py`를 사용하시는 것을 권장합니다.
    (이 함수는 단일 언어용 레거시 코드입니다.)
    """
    index_data = []
    
    if not os.path.exists(CONTENT_DIR):
        os.makedirs(CONTENT_DIR)

    for filename in os.listdir(CONTENT_DIR):
        if filename.endswith(".md"):
            try:
                with open(os.path.join(CONTENT_DIR, filename), "r", encoding="utf-8") as f:
                    post = frontmatter.load(f)
                    
                index_data.append({
                    "file": filename.replace(".md", ""),
                    "name": post.metadata.get("title", filename.replace(".md", "").replace("-", " ").title()),
                    "sneaker": post.metadata.get("sneaker_model", "TBD"),
                    "brand": post.metadata.get("sneaker_brand", "Etc"),
                    "era": post.metadata.get("era", "History"),
                    "image_placeholder": f"/static/img/{filename.replace('.md', '.jpg')}" 
                })
            except Exception as e:
                print(f"⚠️ Error parsing {filename}: {e}")
    
    if index_data:
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Search index updated with {len(index_data)} items.")
    else:
        print("⚠️ No markdown files found to index.")

if __name__ == "__main__":
    print("⚠️ [English Mode] Starting content generation.")
    generate_kicks_content()
    # update_search_index() # 다국어 처리를 위해 여기서는 실행하지 않습니다.