"""
پنل ادمین Flask
────────────────────────────────────────────
تصاویر: Cloudinary
محصولات: Google Sheets
ارسال به کانال: بله (با multipart برای تصویر)
"""

import json, logging, os, io, urllib.error, urllib.request
from functools import wraps

import cloudinary, cloudinary.uploader
from flask import (Flask, flash, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.utils import secure_filename

from sheets import get_all_products, get_categories, add_product, delete_product
from gold_api import get_prices

# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-this-secret-key")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

@app.errorhandler(413)
def too_large(_):
    flash("حجم تصویر بیش از ۸ مگابایت است.", "error")
    return redirect(url_for("dashboard"))

# ─── env ──────────────────────────────────────
BALE_TOKEN = os.getenv("BALE_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")
BALE_API   = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

ALLOWED_EXT  = {"png", "jpg", "jpeg", "webp"}
ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
os.makedirs("uploads", exist_ok=True)

# ─── Cloudinary ───────────────────────────────
CL_NAME   = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
CL_KEY    = os.getenv("CLOUDINARY_API_KEY", "").strip()
CL_SECRET = os.getenv("CLOUDINARY_API_SECRET", "").strip()
CL_OK     = all([CL_NAME, CL_KEY, CL_SECRET])

if CL_OK:
    cloudinary.config(cloud_name=CL_NAME, api_key=CL_KEY,
                      api_secret=CL_SECRET, secure=True)
else:
    log.warning("Cloudinary credentials missing — uploads disabled")


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _allowed(file) -> bool:
    name = secure_filename(file.filename or "")
    ext  = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    mime = (file.mimetype or "").lower()
    return ext in ALLOWED_EXT and mime in ALLOWED_MIME


def _upload_cloudinary(file):
    """آپلود به Cloudinary → (url, public_id)"""
    if not CL_OK:
        raise RuntimeError("Cloudinary not configured")
    r = cloudinary.uploader.upload(
        file.stream, folder="gold-bot/products",
        resource_type="image", unique_filename=True, overwrite=False)
    url = r.get("secure_url", "")
    if not url.startswith("https://"):
        raise RuntimeError(f"Bad Cloudinary URL: {url}")
    return url, r.get("public_id", "")


def _bale_post_json(endpoint: str, payload: dict) -> dict:
    """POST با JSON به بله"""
    data = json.dumps(payload, ensure_ascii=False).encode()
    req  = urllib.request.Request(
        f"{BALE_API}/{endpoint}", data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        log.error("Bale HTTP %s / %s: %s", endpoint, e.code, body)
        return {"ok": False, "error": body}
    except Exception as e:
        log.error("Bale error / %s: %s", endpoint, e)
        return {"ok": False, "error": str(e)}


def _bale_send_photo_binary(chat_id: str, image_url: str, caption: str) -> bool:
    """
    تصویر را ابتدا دانلود می‌کند سپس با multipart/form-data به بله می‌فرستد.
    این روش مطمئن‌ترین راه برای sendPhoto در بله است.
    """
    # دانلود تصویر از Cloudinary
    try:
        img_req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(img_req, timeout=20) as r:
            img_data   = r.read()
            img_ctype  = r.headers.get("Content-Type", "image/jpeg")
    except Exception as e:
        log.error("Could not download image from %s: %s", image_url, e)
        return False

    # ساخت multipart body دستی (بدون کتابخانه اضافی)
    boundary = b"----BaleFormBoundary7MA4YWxkTrZu0gW"
    caption_bytes = caption.encode("utf-8")
    chat_bytes    = chat_id.encode()

    # extension از content-type
    ext_map = {"image/jpeg": "photo.jpg", "image/png": "photo.png", "image/webp": "photo.webp"}
    filename = ext_map.get(img_ctype.split(";")[0].strip(), "photo.jpg")

    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="chat_id"\r\n\r\n' +
        chat_bytes + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="caption"\r\n\r\n' +
        caption_bytes + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="photo"; filename="' +
        filename.encode() + b'"\r\n'
        b"Content-Type: " + img_ctype.encode() + b"\r\n\r\n" +
        img_data + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )

    req = urllib.request.Request(
        f"{BALE_API}/sendPhoto",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            res = json.loads(r.read())
            if res.get("ok"):
                log.info("sendPhoto OK → chat_id=%s", chat_id)
                return True
            log.error("sendPhoto not ok: %s", res)
            return False
    except urllib.error.HTTPError as e:
        log.error("sendPhoto HTTP %s: %s", e.code, e.read().decode(errors="replace"))
        return False
    except Exception as e:
        log.error("sendPhoto error: %s", e)
        return False


def _send_to_bale(chat_id: str, text: str, image_url: str = None) -> bool:
    if not BALE_TOKEN:
        log.error("BALE_TOKEN missing")
        return False
    if not chat_id:
        log.error("chat_id empty")
        return False

    if image_url:
        # روش ۱: ارسال binary (مطمئن‌ترین)
        ok = _bale_send_photo_binary(chat_id, image_url, text)
        if not ok:
            # روش ۲: fallback با URL مستقیم
            log.info("Fallback: trying sendPhoto with URL")
            res = _bale_post_json("sendPhoto", {
                "chat_id": chat_id, "photo": image_url,
                "caption": text, "parse_mode": "Markdown"})
            ok = res.get("ok", False)
        return ok
    else:
        res = _bale_post_json("sendMessage", {
            "chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
        return res.get("ok", False)


# ─────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*a, **kw)
    return d

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASS:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("❌ رمز عبور اشتباه", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────────
#  Routes
# ─────────────────────────────────────────────

@app.route("/admin")
@app.route("/")
@login_required
def dashboard():
    return render_template("admin.html",
        products=get_all_products(),
        categories=get_categories(),
        prices=get_prices())


@app.route("/admin/add", methods=["POST"])
@login_required
def add():
    name     = request.form.get("name","").strip()
    category = request.form.get("category","").strip()
    new_cat  = request.form.get("new_category","").strip()
    price    = request.form.get("price","").strip()
    desc     = request.form.get("description","").strip()
    file     = request.files.get("image")

    if not name or not price:
        flash("❌ نام و قیمت الزامی است", "error")
        return redirect(url_for("dashboard"))

    final_cat  = new_cat if new_cat else category
    image_url  = ""
    public_id  = None

    if file and file.filename:
        if not _allowed(file):
            flash("❌ فرمت مجاز: jpg, png, webp", "error")
            return redirect(url_for("dashboard"))
        try:
            image_url, public_id = _upload_cloudinary(file)
            log.info("Cloudinary upload OK: %s", public_id)
        except Exception:
            log.exception("Cloudinary upload failed")
            flash("❌ آپلود تصویر ناموفق", "error")
            return redirect(url_for("dashboard"))

    try:
        ok = add_product(name, final_cat, price, desc, image_url)
    except Exception:
        log.exception("add_product failed")
        ok = False

    if ok:
        flash(f"✅ محصول «{name}» اضافه شد", "success")
    else:
        if public_id:
            try: cloudinary.uploader.destroy(public_id, resource_type="image")
            except Exception: pass
        flash("❌ خطا در ذخیره در Google Sheets", "error")

    return redirect(url_for("dashboard"))


@app.route("/admin/delete", methods=["POST"])
@login_required
def delete():
    ok = delete_product(request.form.get("id",""))
    flash("✅ حذف شد" if ok else "❌ خطا در حذف", "success" if ok else "error")
    return redirect(url_for("dashboard"))


@app.route("/admin/send", methods=["POST"])
@login_required
def send_to_channel():
    pid      = request.form.get("id","")
    products = get_all_products()
    product  = next((p for p in products if str(p.get("id")) == pid), None)

    if not product:
        flash("❌ محصول یافت نشد", "error")
        return redirect(url_for("dashboard"))

    if not CHANNEL_ID:
        flash("❌ CHANNEL_ID تنظیم نشده", "error")
        return redirect(url_for("dashboard"))

    caption = (
        f"🛍 *{product.get('name','')}*\n"
        f"📂 دسته: {product.get('category','')}\n"
        f"💰 قیمت: {product.get('price','')} تومان\n\n"
        f"{product.get('description','')}\n\n"
        "📲 برای استعلام قیمت روز طلا ربات ما را دنبال کنید"
    )

    img = product.get("image_url") or None
    log.info("Sending product id=%s to channel %s (image=%s)", pid, CHANNEL_ID, bool(img))
    ok = _send_to_bale(CHANNEL_ID, caption, img)

    flash("✅ به کانال ارسال شد" if ok else "❌ ارسال ناموفق — لاگ Render را ببین", 
          "success" if ok else "error")
    return redirect(url_for("dashboard"))


@app.route("/api/gold")
@login_required
def api_gold():
    return jsonify(get_prices() or {})


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory("uploads", filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
