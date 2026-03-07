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
# 모델 설정: 최신 모델 사용 권장
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
    """CSV를 읽어 역사적 인물 x 스니커즈 매칭 대하드라마급 리포트 생성 (영어 전용)"""
    if not os.path.exists(CSV_PATH):
        print("❌ CSV 파일이 없습니다.")
        return

    df = pd.read_csv(CSV_PATH)
    os.makedirs(CONTENT_DIR, exist_ok=True)
    
    print(f"🚀 총 {len(df)}명의 인물에 대한 심층 분석을 시작합니다 (English Mode)...")

    for _, row in df.iterrows():
        name_raw = row['name']
        file_slug = slugify(name_raw)
        file_path = os.path.join(CONTENT_DIR, f"{file_slug}.md")

        # 이미 존재하면 스킵 (덮어쓰기 하려면 이 부분 주석 처리)
        if os.path.exists(file_path):
            print(f"   ⏭️  Skipped: {file_slug}.md (Already exists)")
            continue

        print(f"   👟 Generating deep dive for: {name_raw} ...")
        
        # --- AI 프롬프트 (수정됨: 영어 전용 및 길이 조정) ---
        prompt = f"""
        Act as a professional fashion historian and sneaker columnist (like Highsnobiety or Hypebeast editor).
        
        [Crucial Instruction]
        **WRITE THE ENTIRE OUTPUT STRICTLY IN ENGLISH.** Do not use any other language regardless of the historical figure's origin.

        Target Profile:
        - Name: {name_raw}
        - Era: {row['era']}
        - Role: {row['role']}
        - Traits: {row['keywords']}

        [Task]
        Match a specific sneaker model to this historical figure and write a VERY DETAILED, LONG-FORM article (approx. 1200-1500+ words, extremely detailed).
        
        [Content Requirements]
        1. **Deep Storytelling**: Don't just list facts. Imagine a parallel universe where this figure walks into a sneaker store. The tone should be immersive.
        2. **Sneaker Selection**: Choose a shoe that perfectly matches their personality, history, and color palette.
        3. **Tone**: Witty, professional, trendy, and slightly humorous. Use sneaker slang properly.
        4. **Structure**:
            - **The Fit Check**: A vivid description of their outfit including the shoes.
            - **Historical Connection**: Why this shoe? Connect specific historical events to the shoe's design/history.
            - **Color Theory**: Analyze the color match (e.g., Royal Blue for a King).
            - **Styling Guide**: How would they style it today? (e.g., Traditional robes mixed with modern streetwear).
            - **User Reactions**: Imaginary comments from other historical figures (must be in English).

        [Output Format]
        Output ONLY the raw content for a YAML Frontmatter Markdown file. No markdown code blocks (```).
        
        ---
        title: "{name_raw}"
        title_slug: "{file_slug}"
        sneaker_model: "[Full Model Name]"
        sneaker_brand: "[Brand Name]"
        era: "{row['era']}"
        resell_price: "[Estimated Price in USD]"
        image_prompt: "Cinematic portrait of {name_raw} wearing [Sneaker Model], [Era] clothing mixed with streetwear, highly detailed texture, dramatic lighting, 8k, unreal engine 5 render style."
        ---
        
        ## 🕶️ The Fit Check
        (Write a long, immersive introduction describing the visual impact.)

        ## 👟 Why This Kicks?
        (Deep dive into the connection. Use at least 3-4 paragraphs.)

        ## 🎨 Color & Design DNA
        (Analyze the materials, colors, and silhouette in relation to the figure's history.)

        ## 👕 OOTD Styling Guide
        (Practical styling tips blending historical attire with modern street fashion.)

        ## 💬 Imaginary Reactions
        (Write 3 funny comments from rival historical figures in English.)
        """
        
        try:
            # 긴 텍스트 생성을 위해 max_output_tokens 설정 추가
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=4096, 
                temperature=0.7 
            )
            
            response = MODEL.generate_content(
                prompt,
                generation_config=generation_config
            )
            raw_content = response.text.strip()
            
            # ========================================================
            # [수정된 핵심 로직] 데이터 정제 및 Frontmatter 파싱 강제화
            # ========================================================
            # 1. 불필요한 마크다운 감싸기 제거
            if raw_content.startswith("```markdown"):
                raw_content = raw_content[11:].strip()
            elif raw_content.startswith("```"):
                raw_content = raw_content[3:].strip()
            
            if raw_content.endswith("```"):
                raw_content = raw_content[:-3].strip()

            # 2. 정규식을 이용하여 --- 사이의 내용(YAML)과 그 아래 내용(Body)을 분리
            match = re.search(r'^---\s*\n(.*?)\n---\s*\n(.*)', raw_content, re.DOTALL | re.MULTILINE)
            
            if match:
                yaml_content = match.group(1).strip()
                markdown_body = match.group(2).strip()
                # 완벽한 형식으로 강제 재조립
                final_content = f"---\n{yaml_content}\n---\n\n{markdown_body}"
            else:
                print(f"   ⚠️ Warning: Could not cleanly extract frontmatter for {name_raw}. Formatting might be broken.")
                final_content = raw_content # 실패 시 원본 그대로 저장
            # ========================================================

            # 파일 저장
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(final_content)
            
            print(f"   ✅ Created: {file_slug}.md (Length: {len(final_content)} chars)")
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