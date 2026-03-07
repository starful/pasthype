import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONTENT_DIR = os.path.join(BASE_DIR, "app", "content")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")
TEMPLATE_DIR = os.path.join(BASE_DIR, "app", "templates")

# 데이터 경로
CSV_PATH = os.path.join(DATA_DIR, "figures.csv")
INDEX_PATH = os.path.join(DATA_DIR, "search_index.json")

# 사이트 설정
DOMAIN = "https://pasthype.com"

# 카테고리 (시대/유형)
CATEGORIES = [
    "Joseon Dynasty", "Three Kingdoms", "Western History", 
    "Modern Era", "Mythology"
]