"""
نقطه ورود اصلی — هم ربات هم پنل ادمین رو با هم اجرا می‌کنه
ربات در thread جداگانه، Flask روی پورت اصلی
"""
import threading
import logging
import os

log = logging.getLogger(__name__)


def run_flask():
    from admin_panel import app
    port = int(os.getenv("PORT", 5000))
    log.info(f"🌐 پنل ادمین روی پورت {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def run_bot():
    from bot import run_bot as _run
    _run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # Flask در thread جداگانه
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # ربات در thread اصلی
    run_bot()
