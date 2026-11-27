import os
import json
import requests
import gspread
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials
from substack import Api as SubstackApi
from substack.post import Post as SubstackPost


def get_gsheet():
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1


def publish_facebook(title, hook, content, hashtags, image_url):
    page_id = os.environ["FB_PAGE_ID"]
    token = os.environ["FB_PAGE_TOKEN"]
    caption = f"{title.upper()}\n\n{hook}\n\n{content}\n\n{hashtags}"
    url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
    res = requests.post(url, data={"url": image_url, "caption": caption, "access_token": token}, timeout=30)
    res.raise_for_status()


def publish_substack(title, hook, content, hashtags, image_url):
    pub_url = os.environ["SUBSTACK_PUBLICATION_URL"]
    sid_cookie = os.environ["SUBSTACK_SID"]

    # Khởi tạo kết nối Substack bằng cookie đăng nhập
    api = SubstackApi(
        cookies_string=f"substack.sid={sid_cookie}; connect.sid={sid_cookie}",
        publication_url=pub_url,
    )
    user_id = api.get_user_id()

    # Dựng cấu trúc bài viết Substack chuẩn
    post = SubstackPost(
        title=title,
        subtitle=hook,
        user_id=user_id,
    )

    # Chèn ảnh đầu bài (nếu có)
    if image_url:
        post.add({"type": "captionedImage", "src": image_url})

    # Chèn từng đoạn nội dung
    for line in content.split("\n"):
        if line.strip():
            post.add({"type": "paragraph", "content": [{"content": line.strip(), "type": "text"}]})

    # Chèn hashtags ở cuối bài
    if hashtags:
        post.add({"type": "paragraph", "content": [{"content": hashtags, "type": "text"}]})

    # Tạo bản nháp và xuất bản ngay lập tức
    draft = api.post_draft(post.get_draft())
    api.prepublish_draft(draft.get("id"))
    api.publish_draft(draft.get("id"))


def main():
    vn_tz = timezone(timedelta(hours=7))
    now_vn = datetime.now(vn_tz)
    print(f"Đang kiểm tra lịch đăng lúc: {now_vn.strftime('%Y-%m-%d %H:%M')}")

    sheet = get_gsheet()
    records = sheet.get_all_records()

    for idx, row in enumerate(records, start=2):
        if str(row.get("Status", "")).strip() != "Approved":
            continue

        sched_str = f"{row['Schedule_Date']} {row['Schedule_Time']}"
        try:
            sched_dt = datetime.strptime(sched_str, "%Y-%m-%d %H:%M").replace(tzinfo=vn_tz)
        except ValueError:
            continue

        if now_vn >= sched_dt:
            plat = str(row.get("Platform", "")).lower()
            try:
                if "facebook" in plat:
                    publish_facebook(row["Title"], row["Hook"], row["Content"], row["Hashtags"], row["Image_URL"])
                elif "substack" in plat:
                    publish_substack(row["Title"], row["Hook"], row["Content"], row["Hashtags"], row["Image_URL"])

                sheet.update_cell(idx, 1, "Published")
                print(f"✅ Đã xuất bản thành công dòng {idx}: {row['Title']} ({row['Platform']})")
            except Exception as e:
                print(f"❌ Lỗi khi đăng dòng {idx}: {e}")


if __name__ == "__main__":
    main()