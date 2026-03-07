# --- START OF FILE app/main.py ---
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os
import json
import markdown
import frontmatter
# config에서 필요한 경로들 import
from .config import CONTENT_DIR, STATIC_DIR, TEMPLATE_DIR, INDEX_PATH

# ==========================================
# Firebase Admin SDK 초기화 (로컬/클라우드 자동 대응)
# ==========================================
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
# 동시성 처리를 위해 필요
from fastapi.concurrency import run_in_threadpool

# 클라우드 빌드(Secret Manager) 경로와 로컬 경로를 모두 정의
CLOUD_SECRET_PATH = '/secrets/firebase-key.json'
# ⚠️ 본인이 다운로드 받은 실제 서비스 계정 키 파일명으로 정확히 수정하세요!
LOCAL_SECRET_PATH = 'pasthype-firebase-adminsdk-fbsvc-71c140942c.json' 

# 환경에 따라 적절한 인증 키 파일을 선택합니다.
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

    # Firebase 앱 초기화 (이미 초기화되었는지 확인 후 진행)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    # Firestore 클라이언트 생성
    db = firestore.client()
    print("✅ [System] Firestore database connected successfully.")

except Exception as e:
    print(f"❌ [System] Failed to initialize Firebase: {e}")
    # 에러가 발생하더라도 앱 자체가 죽지 않도록 예외 처리 (디버깅 용이)
    db = None 
# ==========================================

app = FastAPI()

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 지원하는 언어 목록 정의
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

@app.get("/")
async def home(request: Request, lang: str = Query("en", enum=SUPPORTED_LANGS)):
    all_kicks = get_kicks_data()
    filtered_kicks = [item for item in all_kicks if item.get("lang") == lang]
    if not filtered_kicks and lang != 'en':
         filtered_kicks = [item for item in all_kicks if item.get("lang") == 'en']
    return templates.TemplateResponse("index.html", {
        "request": request, "kicks": filtered_kicks, "current_lang": lang
    })

@app.get("/kicks/{slug}")
async def detail(request: Request, slug: str, lang: str = Query("en", enum=SUPPORTED_LANGS)):
    filename = f"{slug}.md"
    if lang == "ko": filename = f"{slug}_ko.md"
    elif lang == "ja": filename = f"{slug}_ja.md"
    file_path = os.path.join(CONTENT_DIR, filename)
    
    if not os.path.exists(file_path):
        return templates.TemplateResponse("404.html", {"request": request, "current_lang": lang}, status_code=404)

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

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "meta": post.metadata,
        "content": content_html,
        "image_url": image_url,
        "current_lang": lang,
        "slug": slug 
    })

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