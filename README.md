# QA-Audit — نسخه‌ی اصلاح‌شده

## نصب سریع
1. محتوای این پوشه را روی پوشه‌ی پروژه‌ی فعلی‌ات کپی/جایگزین کن (همان‌جایی که الان `app.py` هست).
   ساختار همان است: همه‌ی فایل‌های پایتون کنار `app.py` + پوشه‌ی `templates/` با `index.html`.
2. `python3 -m pip install -r requirements.txt` (اگر Playwright/Chromium قبلا نصب نیست:
   `playwright install chromium`).
3. سرور را استاپ/استارت کن و در مرورگر Ctrl+F5.

## فایل‌های تغییرکرده نسبت به نسخه‌ی خودت
- `templates/index.html` — بخش «استخراج لینک از متن» + تغییر دکمه‌ی کلیپ‌بورد
- `qa_core.py` — تشخیص «صفحه‌ی سایت دیگر» با canonical/og:url،
  probe اینترنت قوی‌تر، سقف زمان دانلود تصاویر، هشدارهای پایان اسکن،
  متغیرهای تنظیم زمان (QA_IDLE_WAIT_MS و ...)
- `check_og_image.py` — بازنویسی: همه‌ی تگ‌ها به ترتیب چک می‌شوند
- `check_favicon.py` — سقف زمان
- `check_title.py` — تایتل/توضیحات لاتین از «خطا» به «نیاز به بررسی دستی»

## فایل‌های دست‌نخورده (اما همراهت است برای هم‌خوانی نسخه)
- `app.py`, `check_health.py`, `check_description.py`, `check_source_encoding.py`
- `retry_single.py`, `run_all.py`, `requirements.txt`, `urls.txt`

## گزارش کامل بازبینی
- [audit-report.md](audit-report.md) — شرح دقیق هر تغییر، نتیجه‌ی تست‌ها،
  دو تصمیم که با خودت گذاشتم، و متغیرهای تنظیم زمان.
