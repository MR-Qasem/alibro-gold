"""
ارتباط با Google Sheets برای ذخیره محصولات
─────────────────────────────────────────────
ستون‌های شیت (ردیف اول = هدر):
  A: id | B: name | C: category | D: price | E: description | F: image_url | G: active | H: created_at
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
#  این مقادیر از environment variables خونده میشن
# ─────────────────────────────────────────────
import os

SHEET_ID      = os.getenv("GOOGLE_SHEET_ID", "")       # آی‌دی شیت از URL
SHEET_NAME    = os.getenv("GOOGLE_SHEET_NAME", "products")
SERVICE_CREDS = os.getenv("GOOGLE_CREDS_JSON", "")     # محتوای فایل credentials.json


# ─────────────────────────────────────────────
#  Auth با Google Sheets API
# ─────────────────────────────────────────────
def _get_access_token() -> Optional[str]:
    """توکن دسترسی از Service Account می‌گیره"""
    try:
        import time, base64, hmac, hashlib
        creds = json.loads(SERVICE_CREDS)
        
        # JWT Header
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        
        now = int(time.time())
        claim = {
            "iss":   creds["client_email"],
            "scope": "https://www.googleapis.com/auth/spreadsheets",
            "aud":   "https://oauth2.googleapis.com/token",
            "exp":   now + 3600,
            "iat":   now,
        }
        claim_b64 = base64.urlsafe_b64encode(
            json.dumps(claim).encode()
        ).rstrip(b"=").decode()
        
        # Sign با RSA (نیاز به cryptography package)
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        
        private_key = serialization.load_pem_private_key(
            creds["private_key"].encode(), password=None
        )
        
        signing_input = f"{header}.{claim_b64}".encode()
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
        
        jwt_token = f"{header}.{claim_b64}.{sig_b64}"
        
        # درخواست توکن
        data = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion":  jwt_token,
        }).encode()
        
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())["access_token"]
    except Exception as e:
        print(f"[sheets] خطا در auth: {e}")
        return None


def _sheets_request(method: str, endpoint: str, body: dict = None):
    token = _get_access_token()
    if not token:
        return None
    
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}{endpoint}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[sheets] خطا در request: {e}")
        return None


# ─────────────────────────────────────────────
#  توابع اصلی
# ─────────────────────────────────────────────

def init_sheet():
    """هدر شیت رو مقداردهی اولیه می‌کنه"""
    _sheets_request("PUT", f"/values/{SHEET_NAME}!A1:H1?valueInputOption=RAW", {
        "values": [["id", "name", "category", "price", "description", "image_url", "active", "created_at"]]
    })


def get_all_products() -> list[dict]:
    """همه محصولات فعال رو برمی‌گردونه"""
    result = _sheets_request("GET", f"/values/{SHEET_NAME}!A:H")
    if not result:
        return []
    
    rows = result.get("values", [])
    if len(rows) < 2:
        return []
    
    products = []
    for row in rows[1:]:  # skip header
        while len(row) < 8:
            row.append("")
        if row[6].lower() in ("true", "1", "فعال", "yes"):
            products.append({
                "id":          row[0],
                "name":        row[1],
                "category":    row[2],
                "price":       row[3],
                "description": row[4],
                "image_url":   row[5],
                "active":      row[6],
                "created_at":  row[7],
            })
    return products


def get_categories() -> list[str]:
    """لیست دسته‌بندی‌های یکتا"""
    products = get_all_products()
    return list({p["category"] for p in products if p["category"]})


def add_product(name: str, category: str, price: str,
                description: str, image_url: str) -> bool:
    """یه محصول جدید اضافه می‌کنه"""
    # آخرین ID رو پیدا می‌کنه
    result = _sheets_request("GET", f"/values/{SHEET_NAME}!A:A")
    rows = result.get("values", []) if result else []
    new_id = len(rows)  # ردیف بعدی

    new_row = [
        str(new_id),
        name,
        category,
        price,
        description,
        image_url,
        "true",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
    ]
    
    res = _sheets_request("POST", f"/values/{SHEET_NAME}!A:H:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS", {
        "values": [new_row]
    })
    return res is not None


def delete_product(product_id: str) -> bool:
    """محصول رو غیرفعال می‌کنه (soft delete)"""
    result = _sheets_request("GET", f"/values/{SHEET_NAME}!A:A")
    rows = result.get("values", []) if result else []
    
    for i, row in enumerate(rows):
        if row and row[0] == str(product_id):
            row_num = i + 1
            _sheets_request("PUT", f"/values/{SHEET_NAME}!G{row_num}?valueInputOption=RAW", {
                "values": [["false"]]
            })
            return True
    return False
