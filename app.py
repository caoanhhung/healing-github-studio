import os
import json
import random
import requests
import gspread
import streamlit as st
from datetime import datetime, date, time, timedelta
from dotenv import load_dotenv
from google import genai
from google.oauth2.service_account import Credentials

load_dotenv()

st.set_page_config(page_title="Cao Anh Hùng — Healing Studio", page_icon="🌿", layout="wide")

BRAND_PROMPT = """
Bạn là Cao Anh Hùng — người chia sẻ về chánh niệm thực chứng, chữa lành cảm xúc và sự tỉnh thức trong đời sống hiện đại.
Giọng văn: Trầm ấm, chân thành, sâu sắc, không giáo điều, câu từ tinh gọn và chạm vào nội tâm.
"""
DEFAULT_HASHTAGS = "#CaoAnhHung #ChuaLanh #ChanhNiem #SongTinhThuc #BinhYen"


def get_secret(key: str, default=None):
    """Ưu tiên đọc khóa từ Streamlit Cloud Secrets, nếu không có thì đọc từ biến môi trường."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


def get_gsheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json_str = get_secret("GOOGLE_CREDENTIALS_JSON")
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("service_account.json", scopes=scopes)

    client = gspread.authorize(creds)
    sheet_id = get_secret("GOOGLE_SHEET_ID")
    return client.open_by_key(sheet_id).sheet1


def get_unsplash_images_batch(query, count=10):
    fallback = [
        "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=1080",
        "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=1080",
        "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=1080",
        "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=1080",
        "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=1080",
    ]
    key = get_secret("UNSPLASH_ACCESS_KEY")
    if not key:
        return [fallback[i % len(fallback)] for i in range(count)]
    try:
        res = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "orientation": "landscape", "per_page": max(count, 15), "client_id": key},
            timeout=10,
        )
        if res.status_code == 200 and res.json().get("results"):
            urls = [item["urls"]["regular"] for item in res.json()["results"]]
            random.shuffle(urls)
            return [urls[i % len(urls)] for i in range(count)]
    except Exception:
        pass
    return [fallback[i % len(fallback)] for i in range(count)]


def generate_posts(topic, num_posts):
    api_key = get_secret("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    prompt = f"""
    {BRAND_PROMPT}
    Chủ đề gốc: {topic}
    Hãy viết CHÍNH XÁC {num_posts} bài cho Facebook và {num_posts} bài cho Substack (tổng {num_posts * 2} bài, mỗi bài một góc nhìn khác nhau).
    Trả về CHỈ JSON hợp lệ (không bọc ```json):
    [
      {{
        "platform": "Facebook hoặc Substack",
        "title": "Tiêu đề ngắn gọn",
        "hook": "Câu mở đầu 1-2 dòng thu hút",
        "content": "Nội dung đầy đủ chia đoạn rõ ràng",
        "image_keyword": "2-3 từ khóa tiếng Anh tìm ảnh thiên nhiên/tối giản"
      }}
    ]
    """
    res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = res.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw)


st.title("🌿 Cao Anh Hùng — Healing Content Studio (GitHub Auto)")

with st.sidebar:
    start_date = st.date_input("Ngày bắt đầu rải lịch:", value=date.today() + timedelta(days=1))

c1, c2 = st.columns([4, 1])
topic = c1.text_input("Nhập chủ đề hoặc ý tưởng bài viết:")
num_posts = c2.number_input("Số bài / kênh:", min_value=1, max_value=10, value=1)

if st.button("✨ Tạo nội dung & Ảnh tự động", type="primary") and topic:
    with st.spinner("Đang sáng tạo nội dung và chọn ảnh..."):
        posts = generate_posts(topic, num_posts)
        imgs = get_unsplash_images_batch(posts[0].get("image_keyword", "calm nature"), len(posts))
        for i, p in enumerate(posts):
            p["uid"] = f"{datetime.now().timestamp()}_{i}"
            p["image_url"] = imgs[i]
        st.session_state["posts"] = posts
        st.rerun()

posts = st.session_state.get("posts", [])
if posts:
    st.divider()
    plat_count = {}
    rows_to_push = []

    for idx, p in enumerate(posts):
        uid = p["uid"]
        plat = p["platform"]
        offset = plat_count.get(plat, 0)
        plat_count[plat] = offset + 1
        def_date = start_date + timedelta(days=offset)
        def_time = time(20, 0) if "substack" in plat.lower() else time(7, 30)

        with st.container(border=True):
            h1, h2 = st.columns([7, 1])
            h1.markdown(f"### 📌 {plat} — Bài #{idx + 1}")
            if h2.button("🗑️ Hủy", key=f"del_{uid}", use_container_width=True):
                st.session_state["posts"].pop(idx)
                st.rerun()

            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(p["image_url"], use_container_width=True)
                img_url = st.text_input("Link ảnh:", value=p["image_url"], key=f"img_{uid}")
            with col2:
                d_col, t_col = st.columns(2)
                s_date = d_col.date_input("Ngày đăng", value=def_date, key=f"d_{uid}")
                s_time = t_col.time_input("Giờ đăng", value=def_time, key=f"t_{uid}")
                title = st.text_input("Tiêu đề:", value=p["title"], key=f"ti_{uid}")
                hook = st.text_area("Hook:", value=p["hook"], height=65, key=f"hk_{uid}")
                content = st.text_area("Nội dung:", value=p["content"], height=150, key=f"ct_{uid}")
                tags = st.text_input("Hashtags:", value=DEFAULT_HASHTAGS, key=f"tg_{uid}")

            rows_to_push.append([
                "Approved",
                s_date.strftime("%Y-%m-%d"),
                s_time.strftime("%H:%M"),
                plat,
                title,
                hook,
                content,
                tags,
                img_url,
                topic,
            ])

    if st.button(f"🚀 Lưu TẤT CẢ ({len(rows_to_push)} bài) vào Google Sheets", type="primary", use_container_width=True):
        sheet = get_gsheet()
        sheet.append_rows(rows_to_push)
        st.success(f"🎉 Đã lưu {len(rows_to_push)} bài vào Google Sheets! GitHub Actions sẽ tự động đăng đúng giờ.")
