# 🥇 ربات قیمت طلا — راهنمای کامل راه‌اندازی

## معماری پروژه

```
gold-bot/
├── main.py           ← نقطه شروع (ربات + پنل با هم)
├── bot.py            ← ربات بله چندکاربره
├── admin_panel.py    ← پنل ادمین Flask
├── gold_api.py       ← قیمت طلا از TGJU
├── sheets.py         ← ارتباط با Google Sheets
├── templates/
│   ├── admin.html    ← پنل ادمین
│   └── login.html    ← صفحه ورود
├── uploads/          ← تصاویر محصولات
├── requirements.txt
└── render.yaml       ← تنظیمات Render
```

---

## مرحله ۱ — ساخت Google Sheet و Service Account

### ۱.۱ ساخت شیت
1. به [sheets.google.com](https://sheets.google.com) برو
2. یه شیت جدید بساز، اسمش رو بذار `gold-products`
3. آی‌دی شیت رو از URL کپی کن:
   ```
   https://docs.google.com/spreadsheets/d/[این قسمت]/edit
   ```

### ۱.۲ ساخت Service Account
1. برو به [console.cloud.google.com](https://console.cloud.google.com)
2. یه پروژه جدید بساز
3. **APIs & Services → Enable APIs → Google Sheets API** رو فعال کن
4. **Credentials → Create Credentials → Service Account** بساز
5. روی Service Account کلیک کن → **Keys → Add Key → JSON**
6. فایل JSON دانلود میشه — محتویاتش رو نگه‌دار

### ۱.۳ دسترسی به شیت
1. فایل JSON رو باز کن، مقدار `client_email` رو کپی کن
2. شیت Google رو باز کن → Share → اون ایمیل رو با دسترسی **Editor** اضافه کن

---

## مرحله ۲ — ساخت ربات بله

1. در بله سرچ کن: `@BaleBot`
2. استارت بزن → `/newbot`
3. اسم و username بده
4. توکن رو کپی کن

### گرفتن Chat ID کانال
1. ربات رو به کانال به عنوان **Admin** اضافه کن
2. یه پیام توی کانال بفرست
3. این URL رو باز کن:
   ```
   https://tapi.bale.ai/botTOKEN/getUpdates
   ```
4. دنبال `"chat":{"id":...}` بگرد — عدد منفی (مثلاً `-100123456`) همون کانال هست

---

## مرحله ۳ — Deploy روی Render (رایگان)

1. کد رو روی GitHub (repo خصوصی) آپلود کن
2. به [render.com](https://render.com) برو و ثبت‌نام کن (رایگان)
3. **New → Web Service → Connect GitHub repo** انتخاب کن
4. تنظیمات:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`

5. در بخش **Environment Variables** اضافه کن:

   | کلید | مقدار |
   |------|-------|
   | `BALE_TOKEN` | توکن ربات بله |
   | `CHANNEL_ID` | آی‌دی کانال (مثلاً `-100123456`) |
   | `ADMIN_PASSWORD` | رمز دلخواه برای پنل |
   | `GOOGLE_SHEET_ID` | آی‌دی شیت گوگل |
   | `GOOGLE_CREDS_JSON` | محتوای کامل فایل JSON (کپی-پیست) |
   | `BASE_URL` | آدرس Render (مثلاً `https://gold-bot.onrender.com`) |
   | `ADMIN_IDS` | آی‌دی عددی ادمین‌ها با کاما |

6. Deploy کن!

---

## مرحله ۴ — استفاده

### پنل ادمین
```
https://your-app.onrender.com/admin
```
- محصول اضافه کن (نام، دسته، قیمت، تصویر)
- با دکمه 📢 محصول رو به کانال بفرست
- قیمت طلا رو لحظه‌ای ببین

### ربات بله
- کاربر `/start` می‌زنه → منو با دکمه‌ها ظاهر میشه
- دکمه "استعلام قیمت طلا" → قیمت لحظه‌ای
- دکمه "محصولات" → لیست محصولات با تصویر
- **هر ۱۵ دقیقه** قیمت طلا به کانال ارسال میشه

---

## نکات مهم

- Render plan رایگان بعد از **۱۵ دقیقه بی‌فعالیت** می‌خوابه
- برای همیشه بیدار موندن: از [UptimeRobot](https://uptimerobot.com) (رایگان) استفاده کن — هر ۵ دقیقه یه ping به آدرس Render بفرست
- شیت Google رو روی Private نگه‌دار

---

## مشکل‌یابی

**ربات پاسخ نمیده:**
```
https://tapi.bale.ai/botTOKEN/getMe
```
باید `"ok":true` برگردونه.

**Google Sheets خطا میده:**
مطمئن شو که Service Account با دسترسی Editor به شیت اضافه شده.
