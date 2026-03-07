# --- START OF FILE script/translate_content.py ---
import sys
import os
import frontmatter
import google.generativeai as genai
from dotenv import load_dotenv
import time
import yaml # YAML 처리를 위해 추가

# === 설정 ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(BASE_DIR, "app", "content")
TARGET_LANGS = ["ko", "ja"]

# AI 설정
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = genai.GenerativeModel('gemini-flash-latest')

if not os.path.exists(CONTENT_DIR):
    os.makedirs(CONTENT_DIR)

# === 개선된 AI 번역 프롬프트 ===
def get_translation_prompt(post, lang):
    """
    Frontmatter와 본문을 모두 포함하는 번역 프롬프트를 생성합니다.
    """
    # Frontmatter를 문자열로 변환
    fm_str = yaml.dump(post.metadata, allow_unicode=True, default_flow_style=False)
    
    prompt = f"""
    Act as a professional translator specialized in fashion and culture.
    
    [Task]
    Translate the provided Markdown content into **{lang.upper()}**. This includes specifically marked fields in the YAML Frontmatter and the entire content body.

    [Frontmatter Translation Rules]
    1.  **Translate ONLY** the values of these keys: `title`, `sneaker_model`.
    2.  **DO NOT translate** values of `title_slug`, `sneaker_brand`, `era`, `resell_price`, `image_prompt`.
    3.  Keep the structure and all other keys exactly as they are.

    [Content Body Translation Rules]
    1.  Translate the entire markdown body.
    2.  Keep all markdown formatting (headings, bold, lists, etc.) intact.
    3.  Maintain a witty, professional, and trendy tone appropriate for a fashion article.

    ---
    ---
    {fm_str}
    ---
    {post.content}
    ---
    
    [Output]
    Provide ONLY the fully translated markdown file content, starting with the `---` frontmatter block. No extra text.
    """
    return prompt

# === 번역 수행 ===
def translate_and_save(filename, lang):
    source_path = os.path.join(CONTENT_DIR, filename)
    target_filename = filename.replace(".md", f"_{lang}.md")
    target_path = os.path.join(CONTENT_DIR, target_filename)

    # [수정됨] 이미 번역된 파일이 존재하면 스킵합니다.
    if os.path.exists(target_path):
        print(f"   ⏭️ Skipped {target_filename} (Already exists).")
        return

    try:
        with open(source_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
        
        # 프롬프트 생성 및 AI 호출
        prompt = get_translation_prompt(post, lang)
        
        response = MODEL.generate_content(prompt)
        translated_content = response.text.strip()
        
        # 결과물 검증: Frontmatter가 깨졌는지 확인
        try:
            frontmatter.loads(translated_content)
        except Exception:
            print(f"   ⚠️ Warning: Translation result might have broken frontmatter for {target_filename}. Retrying...")
        
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(translated_content)
            
        print(f"   ✅ Created {target_filename} (Title & Content translated)")
        time.sleep(3) # API 제한 고려하여 대기 시간 증가

    except Exception as e:
        print(f"   ❌ Error translating {filename} to {lang}: {e}")
        time.sleep(5)

# === 메인 실행 ===
def main():
    print(f"🚀 Starting translation (Frontmatter + Content) for: {', '.join(TARGET_LANGS)} ...")
    
    # `yaml` 라이브러리 설치 확인
    try:
        import yaml
    except ImportError:
        print("❌ 'PyYAML' library is missing. Please install it: pip install PyYAML")
        return

    for filename in os.listdir(CONTENT_DIR):
        # 원본 영어 파일만 선택
        if filename.endswith(".md") and not any(f"_{lang}.md" in filename for lang in TARGET_LANGS):
            print(f"\n📄 Processing: {filename}")
            for lang in TARGET_LANGS:
                translate_and_save(filename, lang)

    print("\n✅ Translation complete. Please run 'script/build_index.py' to update the search index.")

if __name__ == "__main__":
    main()