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
            # 긴 텍스트 생성을 위해 max_output_tokens 설정 추가 (모델에 따라 다를 수 있음)
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=4096, # 충분히 긴 길이 확보
                temperature=0.7 # 창의성 조절
            )
            
            response = MODEL.generate_content(
                prompt,
                generation_config=generation_config
            )
            content = response.text.replace("```markdown", "").replace("```", "").strip()
            
            # 파일 저장
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            print(f"   ✅ Created: {file_slug}.md (Length: {len(content)} chars)")
            # API 속도 제한 및 긴 글 생성을 고려하여 대기 시간 증가
            time.sleep(5) 
            
        except Exception as e:
            print(f"   ❌ Error generating content for {name_raw}: {e}")
            # 에러 발생 시 잠시 대기 후 진행 (API 제한 걸렸을 경우 대비)
            time.sleep(10)

def update_search_index():
    """검색 및 리스트 출력을 위한 JSON 인덱스 생성"""
    index_data = []
    
    # content 폴더가 없으면 생성 (에러 방지)
    if not os.path.exists(CONTENT_DIR):
        os.makedirs(CONTENT_DIR)

    for filename in os.listdir(CONTENT_DIR):
        if filename.endswith(".md"):
            try:
                with open(os.path.join(CONTENT_DIR, filename), "r", encoding="utf-8") as f:
                    post = frontmatter.load(f)
                    
                index_data.append({
                    "file": filename.replace(".md", ""),
                    # Frontmatter가 깨졌을 경우를 대비한 기본값 처리 강화
                    "name": post.metadata.get("title", filename.replace(".md", "").replace("-", " ").title()),
                    "sneaker": post.metadata.get("sneaker_model", "TBD"),
                    "brand": post.metadata.get("sneaker_brand", "Etc"),
                    "era": post.metadata.get("era", "History"),
                    # 이미지 확장자는 추후 main.py에서 처리하므로 여기서는 대표적인 것 하나만 지정하거나 비워둠
                    "image_placeholder": f"/static/img/{filename.replace('.md', '.jpg')}" 
                })
            except Exception as e:
                print(f"⚠️ Error parsing {filename}: {e}")
    
    # 인덱스 데이터가 있으면 저장
    if index_data:
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Search index updated with {len(index_data)} items.")
    else:
        print("⚠️ No markdown files found to index.")

if __name__ == "__main__":
    # 기존 한글 콘텐츠가 있다면 삭제하고 다시 시작하는 것을 권장합니다.
    print("⚠️ [English Mode] Starting content generation. Ensure existing Korean content is removed if necessary.")
    generate_kicks_content()
    update_search_index()