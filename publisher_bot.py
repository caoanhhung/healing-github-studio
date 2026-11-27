import os
import json
import requests
import gspread
from datetime import datetime, timezone, timedelta
from google.oauth2.service_account import Credentials

# Múi giờ Việt Nam (UTC+7)
VN_TZ = timezone(timedelta(hours=7))


def get_gsheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("service_account.json", scopes=scopes)

    client = gspread.authorize(creds)
    return client.open_by_key(os.getenv("GOOGLE_SHEET_ID")).sheet1


def publish_to_facebook(caption: str, image_url: str):
    page_id = os.getenv("FB_PAGE_ID", "").strip()
    page_token = os.getenv("FB_PAGE_TOKEN", "").strip()

    if not page_id or not page_token or page_id == "skip" or page_token == "skip":
        raise ValueError("Chưa cấu hình FB_PAGE_ID hoặc FB_PAGE_TOKEN hợp lệ.")

    # Tải ảnh về RAM trước để upload trực tiếp (tránh Facebook chặn link redirect từ Unsplash)
    img_bytes = None
    if image_url:
        try:
            img_res = requests.get(image_url, timeout=15)
            if img_res.status_code == 200:
                img_bytes = img_res.content
        except Exception as e:
            print(f"⚠️ Không tải được ảnh ({e}), chuyển sang đăng bài dạng chữ...")

    if img_bytes:
        url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
        res = requests.post(
            url,
            data={"caption": caption, "access_token": page_token},
            files={"source": ("healing_image.jpg", img_bytes, "image/jpeg")},
            timeout=30,
        )
    else:
        url = f"https://graph.facebook.com/v21.0/{page_id}/feed"
        res = requests.post(
            url,
            data={"message": caption, "access_token": page_token},
            timeout=30,
        )

    if res.status_code != 200:
        # In ra thông báo lỗi chính xác từ Meta API để dễ kiểm soát
        raise RuntimeError(f"Facebook API ({res.status_code}): {res.text}")

    return res.json()


def publish_to_substack(title: str, subtitle: str, content: str, image_url: str):
    from substack import Api
    from substack.post import Post

    pub_url = os.getenv("SUBSTACK_PUBLICATION_URL", "").strip().rstrip("/")
    sid = os.getenv("SUBSTACK_SID", "").strip()

    if not pub_url or not sid:
        raise ValueError("Chưa cấu hình SUBSTACK_PUBLICATION_URL hoặc SUBSTACK_SID.")

    api = Api(
        cookies_string=f"substack.sid={sid}",
        publication_url=pub_url,
    )
    user_id = api.get_user_id()
    post = Post(title=title, subtitle=subtitle, user_id=user_id)

    if image_url:
        post.add({"type": "captioned-image", "src": image_url})

    for para in content.split("\n"):
        if para.strip():
            post.add({"type": "paragraph", "content": para.strip()})

    draft = api.post_draft(post.get_draft())
    api.prepublish_draft(draft.get("id"))
    api.publish_draft(draft.get("id"))
    return draft.get("id")


def main():
    now_vn = datetime.now(VN_TZ)
    print(f"Đang kiểm tra lịch đăng lúc: {now_vn.strftime('%Y-%m-%d %H:%M')}")

    sheet = get_gsheet()
    rows = sheet.get_all_values()

    if len(rows) <= 1:
        print("Chưa có dữ liệu bài viết nào.")
        return

    # Giả định cấu trúc cột:
    # 0: Status | 1: Date | 2: Time | 3: Platform | 4: Title | 5: Hook | 6: Content | 7: Tags | 8: Image_URL
    for row_idx in range(1, len(rows)):
        row = rows[row_idx]
        if len(row) < 7:
            continue

        status = row[0].strip()
        if status.lower() != "approved":
            continue

        s_date = row[1].strip()
        s_time = row[2].strip()
        platform = row[3].strip().lower()
        title = row[4].strip()
        hook = row[5].strip()
        content = row[6].strip()
        tags = row[7].strip() if len(row) > 7 else ""
        img_url = row[8].strip() if len(row) > 8 else ""

        try:
            sched_dt = datetime.strptime(f"{s_date} {s_time}", "%Y-%m-%d %H:%M").replace(tzinfo=VN_TZ)
        except ValueError:
            print(f"⚠️ Dòng {row_idx + 1}: Sai định dạng ngày/giờ ({s_date} {s_time})")
            continue

        if sched_dt > now_vn:
            continue

        try:
            if "facebook" in platform:
                full_caption = f"{title.upper()}\n\n{hook}\n\n{content}\n\n{tags}".strip()
                res = publish_to_facebook(full_caption, img_url)
                print(f"✅ Đã đăng Facebook thành công dòng {row_idx + 1}: {res}")
                sheet.update_cell(row_idx + 1, 1, "Published")

            elif "substack" in platform:
                post_id = publish_to_substack(title, hook, content, img_url)
                print(f"✅ Đã đăng Substack thành công dòng {row_idx + 1} (ID: {post_id})")
                sheet.update_cell(row_idx + 1, 1, "Published")

        except Exception as e:
            print(f"❌ Lỗi khi đăng dòng {row_idx + 1}: {e}")


if __name__ == "__main__":
    main()
