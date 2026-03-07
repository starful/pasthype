# --- START OF FILE app/main.py ---
from fastapi import FastAPI, Request, Query, HTTPException, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os
import json
import markdown
import frontmatter
from datetime import datetime # Sitemap 생성을 위해 추가
# config에서 필요한 경로들 import
from .config import CONTENT_DIR, STATIC_DIR, TEMPLATE_DIR, INDEX_PATH, DOMAIN

# ==========================================
# Firebase Admin SDK 초기화 (로컬/클라우드 자동 대응)
# ==========================================
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from fastapi.concurrency import run_in_threadpool

CLOUD_SECRET_PATH = '/secrets/firebase-key.json'
LOCAL_SECRET_PATH = 'pasthype-firebase-adminsdk-fbsvc-71c140942c.json' 

try:
    if os.path.exists(CLOUD_SECRET_PATH):
        print("☁️ [System] Running on Cloud Run: Using Secret Manager credentials.")
        cred = credentials.Certificate(CLOUD_SECRET_PATH)
    elif os.path.exists(LOCAL_SECRET_PATH):
        print("💻 [System] Running Locally: Using local JSON credentials.")
        cred = credentials.Certificate(LOCAL_SECRET_PATH)
    else:
        print("⚠️ [System] No credentials found! Falling back to Application Default.")
        cred = credentials.ApplicationDefault()

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    print("✅ [System] Firestore database connected successfully.")

except Exception as e:
    print(f"❌ [System] Failed to initialize Firebase: {e}")
    db = None 
# ==========================================

app = FastAPI()

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

SUPPORTED_LANGS = ["en", "ko", "ja"]

def get_client_ip(request: Request):
    """요청한 클라이언트의 IP 주소를 가져옵니다."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0]
    return request.client.host

def get_kicks_data():
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

# ==========================================
# 페이지 라우터 (Home & Detail)
# ==========================================

@app.get("/")
async def home(request: Request, lang: str = Query("en", enum=SUPPORTED_LANGS)):
    all_kicks = get_kicks_data()
    filtered_kicks = [item for item in all_kicks if item.get("lang") == lang]
    if not filtered_kicks and lang != 'en':
         filtered_kicks = [item for item in all_kicks if item.get("lang") == 'en']
         
    # [SEO] 홈 화면용 메타데이터
    site_title = "PastHype | Where Heritage meets Hype"
    site_description = "Discover the ultimate crossover of historical icons and modern sneaker culture. Exploring the kicks of legends."
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "kicks": filtered_kicks, 
        "current_lang": lang,
        "page_title": site_title,
        "page_description": site_description,
        "og_image": f"{DOMAIN}/static/img/default_og.jpg", 
        "current_url": str(request.url)
    })

@app.get("/kicks/{slug}")
async def detail(request: Request, slug: str, lang: str = Query("en", enum=SUPPORTED_LANGS)):
    filename = f"{slug}.md"
    if lang == "ko": filename = f"{slug}_ko.md"
    elif lang == "ja": filename = f"{slug}_ja.md"
    file_path = os.path.join(CONTENT_DIR, filename)
    
    if not os.path.exists(file_path):
        return templates.TemplateResponse("404.html", {
            "request": request, 
            "current_lang": lang,
            "page_title": "Page Not Found | PastHype"
        }, status_code=404)

    with open(file_path, 'r', encoding='utf-8') as f:
        post = frontmatter.load(f)
        content_html = markdown.markdown(post.content)

    image_url = "https://via.placeholder.com/600x800/111/333?text=No+Image"
    potential_extensions = [".jpeg", ".jpg", ".png"]
    for ext in potential_extensions:
        file_check_path = os.path.join(STATIC_DIR, "img", f"{slug}{ext}")
        if os.path.exists(file_check_path):
            image_url = f"/static/img/{slug}{ext}"
            break 

    # [SEO] 상세 페이지용 동적 메타데이터 생성
    title = post.metadata.get('title', 'Unknown Title')
    
    # 본문의 앞부분을 잘라서 Description으로 사용 (HTML 태그 제거 후 150자)
    import re
    clean_text = re.sub(r'<[^>]+>', '', markdown.markdown(post.content))
    description = clean_text[:150].strip() + "..." if len(clean_text) > 150 else clean_text
    
    page_title = f"{title} | PastHype"

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "meta": post.metadata,
        "content": content_html,
        "image_url": image_url,
        "current_lang": lang,
        "slug": slug,
        "page_title": page_title,
        "page_description": description,
        "og_image": f"{DOMAIN}{image_url}",
        "current_url": str(request.url)
    })

# ==========================================
# [신규 추가] SEO를 위한 동적 Sitemap.xml 라우터
# ==========================================
@app.get("/sitemap.xml")
async def sitemap():
    """모든 언어 버전의 페이지 URL을 포함하는 XML 사이트맵을 동적으로 생성합니다."""
    
    # 1. 사이트맵 헤더
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    # 현재 날짜 (lastmod 용)
    current_date = datetime.now().strftime("%Y-%m-%d")

    # 2. 메인 페이지 (언어별) 추가
    for lang in SUPPORTED_LANGS:
        url = f"{DOMAIN}/?lang={lang}" if lang != "en" else f"{DOMAIN}/"
        xml_content += f"""
        <url>
            <loc>{url}</loc>
            <lastmod>{current_date}</lastmod>
            <changefreq>daily</changefreq>
            <priority>1.0</priority>
        </url>"""

    # 3. 상세 페이지 (언어별) 추가
    all_kicks = get_kicks_data()
    for item in all_kicks:
        slug = item.get("slug")
        lang = item.get("lang", "en")
        
        # 언어가 en인 경우 URL 파라미터를 생략하여 깔끔하게 만듦 (선택사항)
        url_suffix = f"?lang={lang}" if lang != "en" else ""
        full_url = f"{DOMAIN}/kicks/{slug}{url_suffix}"
        
        xml_content += f"""
        <url>
            <loc>{full_url}</loc>
            <lastmod>{current_date}</lastmod>
            <changefreq>weekly</changefreq>
            <priority>0.8</priority>
        </url>"""

    # 4. 사이트맵 닫기
    xml_content += '\n</urlset>'

    # Response의 media_type을 application/xml로 명시하여 반환
    return Response(content=xml_content, media_type="application/xml")

@app.get("/robots.txt")
async def robots():
    """robots.txt 파일 제공 (sitemap 경로 포함)"""
    content = f"""User-agent: *
Allow: /

Sitemap: {DOMAIN}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")

# ==========================================
# 좋아요/싫어요 API 엔드포인트
# ==========================================
@app.get("/api/reactions/{slug}")
async def get_reactions(slug: str):
    if db is None:
        return {"likes": 0, "dislikes": 0, "error": "Database not connected"}
        
    doc_ref = db.collection('posts').document(slug)
    doc = await run_in_threadpool(doc_ref.get)

    if doc.exists:
        data = doc.to_dict()
        return {"likes": data.get("likes_count", 0), "dislikes": data.get("dislikes_count", 0)}
    return {"likes": 0, "dislikes": 0}

async def process_reaction(request: Request, slug: str, reaction_type: str):
    if db is None:
         raise HTTPException(status_code=500, detail="Database connection failed")

    client_ip = get_client_ip(request)
    safe_ip = client_ip.replace(".", "_").replace(":", "_")

    post_ref = db.collection('posts').document(slug)
    reaction_ref = post_ref.collection('reactions').document(safe_ip)

    @firestore.transactional
    def update_in_transaction(transaction, post_ref, reaction_ref, new_type):
        try:
            post_doc = next(transaction.get(post_ref))
        except StopIteration:
            post_doc = None

        try:
            reaction_doc = next(transaction.get(reaction_ref))
        except StopIteration:
            reaction_doc = None

        likes_inc = 0
        dislikes_inc = 0

        if post_doc is None or not post_doc.exists:
            transaction.set(post_ref, {"likes_count": 0, "dislikes_count": 0})

        if reaction_doc is None or not reaction_doc.exists:
            if new_type == "like": likes_inc = 1
            else: dislikes_inc = 1
            transaction.set(reaction_ref, {"type": new_type})
            current_type = None
        else:
            current_type = reaction_doc.to_dict().get("type")
            if current_type == new_type:
                if new_type == "like": likes_inc = -1
                else: dislikes_inc = -1
                transaction.delete(reaction_ref)
            else:
                if new_type == "like":
                    likes_inc = 1
                    dislikes_inc = -1
                else:
                    likes_inc = -1
                    dislikes_inc = 1
                transaction.update(reaction_ref, {"type": new_type})

        transaction.update(post_ref, {
            "likes_count": firestore.Increment(likes_inc),
            "dislikes_count": firestore.Increment(dislikes_inc)
        })
        
        return "added" if (reaction_doc is None or not reaction_doc.exists) or current_type != new_type else "removed"

    transaction = db.transaction()
    result = await run_in_threadpool(update_in_transaction, transaction, post_ref, reaction_ref, reaction_type)
    
    updated_doc = await run_in_threadpool(post_ref.get)
    data = updated_doc.to_dict()
    return {
        "status": "success", 
        "action": result,
        "likes": data.get("likes_count", 0), 
        "dislikes": data.get("dislikes_count", 0)
    }

@app.post("/api/like/{slug}")
async def like_post(request: Request, slug: str):
    return await process_reaction(request, slug, "like")

@app.post("/api/dislike/{slug}")
async def dislike_post(request: Request, slug: str):
    return await process_reaction(request, slug, "dislike")