"""
پنل ادمین Flask
────────────────────────────────────────────
مسیرها:
  GET  /admin          → داشبورد + لیست محصولات
  POST /admin/add      → اضافه کردن محصول جدید
  POST /admin/delete   → حذف محصول
  POST /admin/send     → ارسال محصول به کانال بله
  GET  /admin/gold     → نمایش قیمت طلا لحظه‌ای
"""
import cloudinary
import cloudinary.uploader
import os
import json
import uuid
import base64
import urllib.request
import urllib.parse
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from sheets import get_all_products, get_categories, add_product, delete_product
from gold_api import get_prices, build_message

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-this-secret-key")

BALE_TOKEN   = os.getenv("BALE_TOKEN", "")
CHANNEL_ID   = os.getenv("CHANNEL_ID", "")
ADMIN_PASS   = os.getenv("ADMIN_PASSWORD", "admin123")  # رمز ورود پنل
BALE_API     = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

UPLOAD_FOLDER = "uploads"
ALLOWED_EXT   = {"png", "jpg", "jpeg", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─────────────────────────────────────────────
#  Auth ساده با session
# ─────────────────────────────────────────────
from functools import wraps
from flask import session

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASS:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("❌ رمز عبور اشتباه است", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────────
#  داشبورد
# ─────────────────────────────────────────────
@app.route("/admin")
@app.route("/")
@login_required
def dashboard():
    products   = get_all_products()
    categories = get_categories()
    prices     = get_prices()
    return render_template("admin.html",
                           products=products,
                           categories=categories,
                           prices=prices)


# ─────────────────────────────────────────────
#  اضافه کردن محصول
# ─────────────────────────────────────────────
@app.route("/admin/add", methods=["POST"])
@login_required
def add():
    name        = request.form.get("name", "").strip()
    category    = request.form.get("category", "").strip()
    new_cat     = request.form.get("new_category", "").strip()
    price       = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    file        = request.files.get("image")

    if not name or not price:
        flash("❌ نام و قیمت الزامی است", "error")
        return redirect(url_for("dashboard"))

    final_cat = new_cat if new_cat else category
    image_url = ""

  # Cloudinary Configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)
    # آپلود تصویر
    if file and file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext in ALLOWED_EXT:
            filename  = f"{uuid.uuid4().hex}.{ext}"
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(save_path)
            # URL عمومی تصویر (بعد از deploy روی Render)
            base_url  = os.getenv("BASE_URL", "http://localhost:5000")
            image_url = f"{base_url}/uploads/{filename}"
        else:
            flash("❌ فرمت تصویر مجاز نیست (jpg, png, webp)", "error")
            return redirect(url_for("dashboard"))

    ok = add_product(name, final_cat, price, description, image_url)
    if ok:
        flash(f"✅ محصول «{name}» با موفقیت اضافه شد", "success")
    else:
        flash("❌ خطا در ذخیره محصول", "error")

    return redirect(url_for("dashboard"))


# ─────────────────────────────────────────────
#  حذف محصول
# ─────────────────────────────────────────────
@app.route("/admin/delete", methods=["POST"])
@login_required
def delete():
    product_id = request.form.get("id", "")
    ok = delete_product(product_id)
    if ok:
        flash("✅ محصول حذف شد", "success")
    else:
        flash("❌ خطا در حذف محصول", "error")
    return redirect(url_for("dashboard"))


# ─────────────────────────────────────────────
#  ارسال محصول به کانال بله
# ─────────────────────────────────────────────
@app.route("/admin/send", methods=["POST"])
@login_required
def send_to_channel():
    product_id = request.form.get("id", "")
    products   = get_all_products()
    product    = next((p for p in products if p["id"] == product_id), None)

    if not product:
        flash("❌ محصول یافت نشد", "error")
        return redirect(url_for("dashboard"))

    caption = (
        f"🛍 *{product['name']}*\n"
        f"📂 دسته: {product['category']}\n"
        f"💰 قیمت: {product['price']} تومان\n\n"
        f"{product['description']}\n\n"
        f"📲 برای استعلام قیمت روز طلا ربات ما را دنبال کنید"
    )

    result = _send_to_bale(CHANNEL_ID, caption, product.get("image_url"))

    if result:
        flash("✅ محصول به کانال ارسال شد", "success")
    else:
        flash("❌ خطا در ارسال به کانال", "error")

    return redirect(url_for("dashboard"))


def _send_to_bale(chat_id: str, text: str, image_url: str = None) -> bool:
    endpoint = "sendPhoto" if image_url else "sendMessage"
    payload  = {
        "chat_id":    chat_id,
        "parse_mode": "Markdown",
    }
    if image_url:
        payload["photo"]   = image_url
        payload["caption"] = text
    else:
        payload["text"] = text

    data = json.dumps(payload).encode()
    url  = f"{BALE_API}/{endpoint}"
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read())
            return res.get("ok", False)
    except Exception as e:
        print(f"[send_to_bale] {e}")
        return False


# ─────────────────────────────────────────────
#  API endpoint برای قیمت طلا (AJAX)
# ─────────────────────────────────────────────
@app.route("/api/gold")
@login_required
def api_gold():
    prices = get_prices()
    return jsonify(prices or {})


# ─────────────────────────────────────────────
#  سرو کردن تصاویر آپلودشده
# ─────────────────────────────────────────────
from flask import send_from_directory

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
