"""دریافت قیمت طلا از TGJU — بدون API Key"""
import urllib.request
import json
from datetime import datetime


TGJU_URL = "https://call.tgju.org/ajax.json"


def _fetch() -> dict:
    req = urllib.request.Request(TGJU_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _parse(item):
    if not item:
        return "—", 0.0
    raw = item.get("p", "0").replace(",", "")
    d   = item.get("d", "0")
    try:
        price = int(raw)
        fmt   = f"{price:,}"
    except Exception:
        fmt = raw
        price = 0
    try:
        change = float(str(d).replace(",", "").replace("+", ""))
    except Exception:
        change = 0.0
    return fmt, change


def arrow(change: float) -> str:
    return "🔺" if change > 0 else ("🔻" if change < 0 else "➖")


def get_prices() -> dict | None:
    try:
        data = _fetch()
        c    = data.get("current", {})

        g18_v, g18_d = _parse(c.get("geram18"))
        g24_v, g24_d = _parse(c.get("geram24"))
        mi_v,  mi_d  = _parse(c.get("mithqal"))
        se_v,  se_d  = _parse(c.get("sekeb"))
        nim_v, nim_d = _parse(c.get("nim"))
        rob_v, rob_d = _parse(c.get("rob"))
        oz_v,  oz_d  = _parse(c.get("ounce"))
        usd_v, usd_d = _parse(c.get("price_dollar_rl"))

        return {
            "geram18": (g18_v, g18_d),
            "geram24": (g24_v, g24_d),
            "mithqal": (mi_v,  mi_d),
            "sekeb":   (se_v,  se_d),
            "nim":     (nim_v, nim_d),
            "rob":     (rob_v, rob_d),
            "ounce":   (oz_v,  oz_d),
            "usd":     (usd_v, usd_d),
            "time":    datetime.now().strftime("%H:%M  %d/%m/%Y"),
        }
    except Exception as e:
        print(f"[gold_api] خطا: {e}")
        return None


def build_message(p: dict) -> str:
    def line(label, key):
        v, d = p[key]
        return f"  {label}: {v} {arrow(d)}"

    return (
        "🥇 *قیمت لحظه‌ای طلا و سکه*\n"
        f"🕐 {p['time']}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💛 *طلا (تومان)*\n"
        f"{line('گرم ۱۸ عیار ', 'geram18')}\n"
        f"{line('گرم ۲۴ عیار ', 'geram24')}\n"
        f"{line('مثقال        ', 'mithqal')}\n\n"
        "🪙 *سکه*\n"
        f"{line('سکه تمام    ', 'sekeb')}\n"
        f"{line('نیم سکه     ', 'nim')}\n"
        f"{line('ربع سکه     ', 'rob')}\n\n"
        "🌍 *جهانی*\n"
        f"{line('اونس (دلار) ', 'ounce')}\n"
        f"{line('دلار (ریال) ', 'usd')}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📡 _tgju.org_"
    )
