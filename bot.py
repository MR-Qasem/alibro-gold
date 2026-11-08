"""
ربات بله — چندکاربره
────────────────────────────────────────────
دکمه‌ها:
  💰 استعلام قیمت طلا
  🛒 مشاهده محصولات
  📋 دسته‌بندی‌ها
"""

import os
import json
import time
import logging
import urllib.request
import urllib.parse
import threading
from gold_api import get_prices, build_message
from sheets import get_all_products, get_categories

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BALE_TOKEN   = os.getenv("BALE_TOKEN", "")
CHANNEL_ID   = os.getenv("CHANNEL_ID", "")       # آی‌دی کانال برای ارسال خودکار
ADMIN_IDS    = os.getenv("ADMIN_IDS", "").split(",")  # آی‌دی ادمین‌ها با کاما

BALE_API     = f"https://tapi.bale.ai/bot{BALE_TOKEN}"
SCHEDULE_MIN = 15   # هر ۱۵ دقیقه به کانال بفرسته

# ───────────────────────────────────────────
#  HTTP helpers
# ───────────────────────────────────────────
def _post(endpoint: str, payload: dict) -> dict:
    url  = f"{BALE_API}/{endpoint}"
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        log.error(f"[POST {endpoint}] {e}")
        return {}


def _get(endpoint: str, params: dict = None) -> dict:
    url = f"{BALE_API}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        log.error(f"[GET {endpoint}] {e}")
        return {}


# ───────────────────────────────────────────
#  ارسال پیام
# ───────────────────────────────────────────
def send_text(chat_id, text: str, keyboard=None) -> dict:
    payload = {
        "chat_id":    str(chat_id),
        "text":       text,
        "parse_mode": "Markdown",
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    return _post("sendMessage", payload)


def send_photo(chat_id, photo_url: str, caption: str = "", keyboard=None) -> dict:
    payload = {
        "chat_id": str(chat_id),
        "photo":   photo_url,
        "caption": caption,
        "parse_mode": "Markdown",
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    return _post("sendPhoto", payload)


def answer_callback(callback_query_id: str, text: str = "") -> dict:
    return _post("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
    })


# ───────────────────────────────────────────
#  کیبوردها
# ───────────────────────────────────────────
MAIN_KEYBOARD = {
    "inline_keyboard": [
        [{"text": "💰 استعلام قیمت طلا",    "callback_data": "gold_price"}],
        [{"text": "🛒 محصولات",              "callback_data": "products"}],
        [{"text": "📋 دسته‌بندی‌ها",          "callback_data": "categories"}],
    ]
}

def back_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🔙 بازگشت", "callback_data": "main_menu"}]
        ]
    }

def category_keyboard(cats: list[str]):
    rows = [[{"text": f"📂 {c}", "callback_data": f"cat_{c}"}] for c in cats]
    rows.append([{"text": "🔙 بازگشت", "callback_data": "main_menu"}])
    return {"inline_keyboard": rows}


# ───────────────────────────────────────────
#  هندلرها
# ───────────────────────────────────────────
def handle_start(chat_id, first_name: str):
    text = (
        f"سلام {first_name} عزیز 👋\n\n"
        "🥇 به ربات قیمت طلا خوش اومدید!\n\n"
        "از منوی زیر می‌تونید:\n"
        "• قیمت لحظه‌ای طلا و سکه رو ببینید\n"
        "• محصولات طلا‌فروشی رو مرور کنید\n"
        "• بر اساس دسته‌بندی جستجو کنید\n\n"
        "_قیمت‌ها هر ۱۵ دقیقه به‌روز می‌شن_ 🔄"
    )
    send_text(chat_id, text, MAIN_KEYBOARD)


def handle_gold_price(chat_id):
    send_text(chat_id, "⏳ در حال دریافت قیمت‌ها...")
    prices = get_prices()
    if prices:
        send_text(chat_id, build_message(prices), back_keyboard())
    else:
        send_text(chat_id, "⚠️ خطا در دریافت قیمت. لطفاً دوباره امتحان کنید.", back_keyboard())


def handle_products(chat_id, category: str = None):
    products = get_all_products()
    if category:
        products = [p for p in products if p["category"] == category]

    if not products:
        send_text(chat_id, "❌ محصولی یافت نشد.", back_keyboard())
        return

    for p in products[:10]:  # حداکثر ۱۰ تا نمایش بده
        caption = (
            f"*{p['name']}*\n"
            f"📂 دسته: {p['category']}\n"
            f"💰 قیمت: {p['price']} تومان\n\n"
            f"{p['description']}"
        )
        if p.get("image_url"):
            send_photo(chat_id, p["image_url"], caption)
        else:
            send_text(chat_id, caption)
        time.sleep(0.3)

    send_text(chat_id, "─────────────\n🔙 بازگشت به منو", back_keyboard())


def handle_categories(chat_id):
    cats = get_categories()
    if not cats:
        send_text(chat_id, "❌ دسته‌بندی‌ای یافت نشد.", back_keyboard())
        return
    send_text(chat_id, "📋 *دسته‌بندی‌ها*\nیک دسته را انتخاب کنید:", category_keyboard(cats))


# ───────────────────────────────────────────
#  پردازش آپدیت‌ها
# ───────────────────────────────────────────
def process_update(update: dict):
    # پیام متنی
    if "message" in update:
        msg     = update["message"]
        chat_id = msg["chat"]["id"]
        text    = msg.get("text", "")
        name    = msg["from"].get("first_name", "کاربر")

        if text in ("/start", "start"):
            handle_start(chat_id, name)

    # callback از دکمه‌های inline
    elif "callback_query" in update:
        cb      = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        data    = cb.get("data", "")
        cb_id   = cb["id"]

        answer_callback(cb_id)

        if data == "main_menu":
            handle_start(chat_id, cb["from"].get("first_name", "کاربر"))
        elif data == "gold_price":
            handle_gold_price(chat_id)
        elif data == "products":
            handle_products(chat_id)
        elif data == "categories":
            handle_categories(chat_id)
        elif data.startswith("cat_"):
            handle_products(chat_id, category=data[4:])


# ───────────────────────────────────────────
#  ارسال خودکار به کانال هر ۱۵ دقیقه
# ───────────────────────────────────────────
def scheduler_loop():
    log.info(f"⏰ Scheduler شروع — هر {SCHEDULE_MIN} دقیقه به کانال می‌فرسته")
    while True:
        time.sleep(SCHEDULE_MIN * 60)
        if CHANNEL_ID:
            prices = get_prices()
            if prices:
                result = send_text(CHANNEL_ID, build_message(prices), MAIN_KEYBOARD)
                if result.get("ok"):
                    log.info("📢 قیمت به کانال ارسال شد.")
                else:
                    log.warning(f"⚠️ ارسال به کانال ناموفق: {result}")



def _get_long(endpoint: str, params: dict = None) -> dict:
    """Long-polling GET — urlopen timeout باید از polling timeout بیشتر باشه"""
    url = f"{BALE_API}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            return json.loads(r.read())
    except Exception as e:
        log.error(f"[GET_LONG {endpoint}] {e}")
        return {}

# ───────────────────────────────────────────
#  حلقه اصلی polling
# ───────────────────────────────────────────
def run_bot():
    log.info("🤖 ربات شروع به کار کرد")

    # تست اتصال
    me = _get("getMe")
    if me.get("ok"):
        log.info(f"✅ ربات: @{me['result'].get('username')}")
    else:
        log.error("❌ توکن اشتباه است!")
        return

    # اجرای scheduler در thread جداگانه
    if CHANNEL_ID:
        t = threading.Thread(target=scheduler_loop, daemon=True)
        t.start()

    offset = 0
    while True:
        try:
            result = _get_long("getUpdates", {"offset": offset, "timeout": 20})
            updates = result.get("result", [])
            for update in updates:
                try:
                    process_update(update)
                except Exception as e:
                    log.error(f"خطا در پردازش آپدیت: {e}")
                offset = update["update_id"] + 1
        except Exception as e:
            log.error(f"خطا در polling: {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
