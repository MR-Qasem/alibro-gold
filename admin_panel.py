"""
پنل ادمین Flask
────────────────────────────────────────────
مسیرها:
  GET  /admin          → داشبورد + لیست محصولات
  POST /admin/add      → اضافه کردن محصول جدید
  POST /admin/delete   → حذف محصول
  POST /admin/send     → ارسال محصول به کانال بله
  GET  /admin/gold     → نمایش قیمت طلا لحظه‌ای

ذخیره تصاویر جدید: Cloudinary
ذخیره اطلاعات محصولات: Google Sheets
"""

import json
import logging
import os
import urllib.error
import urllib.request
from functools import wraps

import cloudinary
import cloudinary.uploader
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from sheets import get_all_products, get_categories, add_product, delete_product
from gold_api import get_prices


# ─────────────────────────────────────────────
#  App & logging
# ─────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "change-this-secret-key")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

# محدودیت حجم کل درخواست آپلود (۸ مگابایت)
MAX_IMAGE_SIZE = 8 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_SIZE

@app.errorhandler(413)
def request_entity_too_large(_error):
    flash("حجم تصویر بیش از حد مجاز است (حداکثر ۸ مگابایت).", "error")
    return redirect(url_for("dashboard"))


# ─────────────────────────────────────────────
#  Environment variables
# ─────────────────────────────────────────────

BALE_TOKEN = os.getenv("BALE_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")
BALE_API = f"https://tapi.bale.ai/bot{BALE_TOKEN}"

UPLOAD_FOLDER = "uploads"
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
ALLOWED_MIMETYPES = {"image/png", "image/jpeg", "image/webp"}

# این پوشه فقط برای سازگاری با تصاویر قدیمی نگه داشته شده است.
# تصاویر جدید در این مسیر ذخیره نمی‌شوند.
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# پیکربندی Cloudinary در سطح ماژول انجام می‌شود، نه داخل route.
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "").strip()
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "").strip()

CLOUDINARY_CONFIGURED = all(
    [CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]
)

if CLOUDINARY_CONFIGURED:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )
else:
    logger.warning(
        "Cloudinary credentials are incomplete. Image uploads will be unavailable."
    )


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _allowed_image(file):
    """بررسی پسوند و MIME تصویر."""
    original_name = secure_filename(file.filename or "")
    if "." not in original_name:
        return False

    extension = original_name.rsplit(".", 1)[-1].lower()
    mimetype = (file.mimetype or "").lower()

    return extension in ALLOWED_EXT and mimetype in ALLOWED_MIMETYPES


def _upload_image_to_cloudinary(file):
    """
    تصویر را مستقیماً از stream به Cloudinary می‌فرستد.
    خروجی: (secure_url, public_id)
    """
    if not CLOUDINARY_CONFIGURED:
        raise RuntimeError(
            "Cloudinary is not configured. Check CLOUDINARY_CLOUD_NAME, "
            "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET."
        )

    result = cloudinary.uploader.upload(
        file.stream,
        folder="gold-bot/products",
        resource_type="image",
        use_filename=False,
        unique_filename=True,
        overwrite=False,
    )

    image_url = result.get("secure_url")
    public_id = result.get("public_id")

    if not image_url or not image_url.startswith("https://"):
        raise RuntimeError("Cloudinary did not return a valid HTTPS image URL.")

    return image_url, public_id


# ─────────────────────────────────────────────
#  Auth ساده با session
# ─────────────────────────────────────────────

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
    products = get_all_products()
    categories = get_categories()
    prices = get_prices()

    return render_template(
        "admin.html",
        products=products,
        categories=categories,
        prices=prices,
    )


# ─────────────────────────────────────────────
#  اضافه کردن محصول
# ─────────────────────────────────────────────

@app.route("/admin/add", methods=["POST"])
@login_required
def add():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    new_cat = request.form.get("new_category", "").strip()
    price = request.form.get("price", "").strip()
    description = request.form.get("description", "").strip()
    file = request.files.get("image")

    if not name or not price:
        flash("❌ نام و قیمت الزامی است", "error")
        return redirect(url_for("dashboard"))

    final_cat = new_cat if new_cat else category
    image_url = ""
    uploaded_public_id = None

    # اگر تصویری انتخاب شده باشد، ابتدا آن را روی Cloudinary آپلود می‌کنیم.
    if file and file.filename:
        if not _allowed_image(file):
            flash("❌ فرمت تصویر مجاز نیست (jpg, jpeg, png, webp)", "error")
            return redirect(url_for("dashboard"))

        try:
            image_url, uploaded_public_id = _upload_image_to_cloudinary(file)
            logger.info("Image uploaded to Cloudinary: %s", uploaded_public_id)

        except Exception:
            logger.exception("Cloudinary image upload failed")
            flash("❌ آپلود تصویر ناموفق بود؛ محصول ذخیره نشد.", "error")
            return redirect(url_for("dashboard"))

    # پس از آپلود موفق تصویر، اطلاعات محصول در Google Sheets ذخیره می‌شود.
    try:
        ok = add_product(
            name,
            final_cat,
            price,
            description,
            image_url,
        )
    except Exception:
        logger.exception("Saving product to Google Sheets failed")
        ok = False

    if ok:
        flash(f"✅ محصول «{name}» با موفقیت اضافه شد", "success")
    else:
        # اگر ثبت محصول در شیت شکست خورد، تصویر آپلودشده را از Cloudinary پاک می‌کنیم
        # تا فایل بلااستفاده در فضای ابری باقی نماند.
        if uploaded_public_id:
            try:
                cloudinary.uploader.destroy(
                    uploaded_public_id,
                    resource_type="image",
                )
            except Exception:
                logger.exception(
                    "Could not clean up orphaned Cloudinary image: %s",
                    uploaded_public_id,
                )

        flash("❌ خطا در ذخیره محصول در Google Sheets", "error")

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
    products = get_all_products()
    product = next((p for p in products if str(p.get("id")) == product_id), None)

    if not product:
        flash("❌ محصول یافت نشد", "error")
        return redirect(url_for("dashboard"))

    caption = (
        f"🛍 *{product.get('name', '')}*\n"
        f"📂 دسته: {product.get('category', '')}\n"
        f"💰 قیمت: {product.get('price', '')} تومان\n\n"
        f"{product.get('description', '')}\n\n"
        "📲 برای استعلام قیمت روز طلا ربات ما را دنبال کنید"
    )

    if not CHANNEL_ID:
        logger.error("CHANNEL_ID is not configured.")
        flash("❌ شناسه کانال در تنظیمات سرور تعریف نشده است.", "error")
        return redirect(url_for("dashboard"))

    result = _send_to_bale(
        CHANNEL_ID,
        caption,
        product.get("image_url") or None,
    )

    if result:
        flash("✅ محصول به کانال ارسال شد", "success")
    else:
        flash("❌ ارسال به کانال ناموفق بود؛ لاگ Render را بررسی کن.", "error")

    return redirect(url_for("dashboard"))


def _send_to_bale(chat_id: str, text: str, image_url: str = None) -> bool:
    """ارسال متن یا تصویر به Bale و ثبت پاسخ خطا در لاگ."""
    if not BALE_TOKEN:
        logger.error("BALE_TOKEN is not configured.")
        return False

    endpoint = "sendPhoto" if image_url else "sendMessage"
    payload = {
        "chat_id": chat_id,
        "parse_mode": "Markdown",
    }

    if image_url:
        payload["photo"] = image_url
        payload["caption"] = text
    else:
        payload["text"] = text

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"{BALE_API}/{endpoint}"

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            result = json.loads(response_body)

            if not result.get("ok", False):
                logger.error("Bale API returned an unsuccessful response: %s", response_body)
                return False

            return True

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        logger.error(
            "Bale HTTP error %s: %s",
            error.code,
            error_body,
        )
        return False

    except urllib.error.URLError as error:
        logger.error("Bale connection error: %s", error)
        return False

    except json.JSONDecodeError:
        logger.exception("Bale API returned invalid JSON.")
        return False

    except Exception:
        logger.exception("Unexpected error while sending message to Bale.")
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
#  سرو کردن تصاویر قدیمی
# ─────────────────────────────────────────────
# این route فقط برای فایل‌هایی است که قبلاً در uploads ذخیره شده‌اند.
# تصاویر جدید از Cloudinary ارائه می‌شوند.

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
