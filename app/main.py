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
# Firebase Admin SDK 초기화
# ==========================================
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
# 동시성 처리를 위해 필요
from fastapi.concurrency import run_in_threadpool

# 서비스 계정 키 파일 경로 설정 (실제 파일명으로 수정 필요!)
cred = credentials.Certificate('pasthype-firebase-adminsdk-fbsvc-71c140942c.json')

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
# ==========================================


app = FastAPI()

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 지원하는 언어 목록 정의
SUPPORTED_LANGS = ["en", "ko", "ja"]

# ... (get_kicks_data, home 라우터 등 기존 코드 유지) ...
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
    # ... (기존 detail 라우터 로직 유지) ...
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
# [신규 추가] 좋아요/싫어요 API 엔드포인트
# ==========================================

def get_client_ip(request: Request):
    """요청한 클라이언트의 IP 주소를 가져옵니다."""
    # 프록시를 거쳐오는 경우를 대비해 x-forwarded-for 헤더를 먼저 확인
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0]
    return request.client.host

@app.get("/api/reactions/{slug}")
async def get_reactions(slug: str):
    """현재 게시물의 좋아요/싫어요 카운트를 조회합니다."""
    # Firestore는 블로킹 I/O이므로 스레드풀에서 실행하여 서버 멈춤 방지
    doc_ref = db.collection('posts').document(slug)
    doc = await run_in_threadpool(doc_ref.get)

    if doc.exists:
        data = doc.to_dict()
        return {"likes": data.get("likes_count", 0), "dislikes": data.get("dislikes_count", 0)}
    return {"likes": 0, "dislikes": 0}

async def process_reaction(request: Request, slug: str, reaction_type: str):
    """좋아요/싫어요 처리 핵심 로직 (트랜잭션 사용)"""
    client_ip = get_client_ip(request)
    safe_ip = client_ip.replace(".", "_").replace(":", "_")

    post_ref = db.collection('posts').document(slug)
    reaction_ref = post_ref.collection('reactions').document(safe_ip)

    # [수정] 트랜잭션 함수 내부 로직 변경
    @firestore.transactional
    def update_in_transaction(transaction, post_ref, reaction_ref, new_type):
        # 1. transaction.get()은 제너레이터를 반환하므로 next()로 DocumentSnapshot을 꺼냅니다.
        #    만약 문서가 없으면 None이 반환될 수 있으므로 처리합니다.
        try:
            post_doc = next(transaction.get(post_ref))
        except StopIteration:
            post_doc = None # 문서가 없는 경우

        try:
            reaction_doc = next(transaction.get(reaction_ref))
        except StopIteration:
            reaction_doc = None # 문서가 없는 경우

        likes_inc = 0
        dislikes_inc = 0

        # 2. post_doc이 None이거나 존재하지 않으면 새로 생성
        if post_doc is None or not post_doc.exists:
            transaction.set(post_ref, {"likes_count": 0, "dislikes_count": 0})

        # 3. reaction_doc이 None이거나 존재하지 않으면 (첫 반응)
        if reaction_doc is None or not reaction_doc.exists:
            if new_type == "like": likes_inc = 1
            else: dislikes_inc = 1
            transaction.set(reaction_ref, {"type": new_type})
            current_type = None
        else:
            # 4. 이미 반응한 적이 있는 경우
            current_type = reaction_doc.to_dict().get("type")
            if current_type == new_type:
                # 같은 버튼을 또 누름 -> 반응 취소 (토글)
                if new_type == "like": likes_inc = -1
                else: dislikes_inc = -1
                transaction.delete(reaction_ref)
            else:
                # 다른 버튼을 누름 -> 변경
                if new_type == "like":
                    likes_inc = 1
                    dislikes_inc = -1
                else:
                    likes_inc = -1
                    dislikes_inc = 1
                transaction.update(reaction_ref, {"type": new_type})

        # 메인 게시물 문서의 카운트 업데이트
        transaction.update(post_ref, {
            "likes_count": firestore.Increment(likes_inc),
            "dislikes_count": firestore.Increment(dislikes_inc)
        })
        
        # 최종 상태 반환
        return "added" if (reaction_doc is None or not reaction_doc.exists) or current_type != new_type else "removed"

    # 트랜잭션 실행 (변경 없음)
    transaction = db.transaction()
    result = await run_in_threadpool(update_in_transaction, transaction, post_ref, reaction_ref, reaction_type)
    
    # 업데이트된 최신 카운트 조회 (변경 없음)
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