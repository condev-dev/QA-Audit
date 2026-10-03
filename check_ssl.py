# -*- coding: utf-8 -*-
"""
check_ssl.py - بررسی گواهی SSL
اجرای تنها:  python check_ssl.py
خروجی:       reports/ssl_report.csv

منطق جدید (پس از یکدست‌سازی):
  - این چک دیگر یک Playwright مجزا بالا نمی‌آورد. اطلاعات گواهی را از همان اسنپ‌شات
    مشترکی که qa_core برای کل سایت ساخته، می‌خواند (snap['ssl_valid_to'] و ...).
  - اگر صفحه اصلی سالم نیست (DNS/offline/filter/foreign)، content_gate خروجی
    «بررسی نشد» می‌دهد — هم‌خوان با بقیه چک‌ها.
  - اگر سایت http بود (یعنی اصلاً SSL ندارد) خطای قطعی.
  - اگر گواهی تاریخ انقضا ندارد (کم‌پیش‌آمد ولی ممکن) → سالم.
  - اگر منقضی شده → خطا.
  - اگر <= qc.SSL_DAYS_WARN روز باقی مانده → نیاز به بررسی دستی.
  - در غیر این صورت → سالم.

**مزیت نسبت به نسخه‌ی قدیمی:**
  1. هر سایت دیگر دو بار باز نمی‌شود (نصف ترافیک).
  2. وقتی health=err (مثلاً گواهی خراب) این چک هم err می‌دهد، نه سالم.
  3. وقتی سایت ریدایرکت می‌شود، SSL همان دامنه‌ی نهایی را گزارش می‌کند، نه دامنه‌ی قدیمی.
"""
import datetime
import sys
import qa_core as qc

TOOL_ID = 'ssl'
CSV_NAME = 'ssl_report.csv'
FIELDS = ['URL', 'Status', 'Details']


def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    if gate:
        return {'Status': gate, 'Details': '-'}

    fin = (snap.get('final_url') or snap.get('url') or '').lower()
    # اگر سایت http است یا به http منتقل شده، SSL ندارد.
    if fin.startswith('http://'):
        return {'Status': 'خطا: اتصال فاقد SSL (پروتکل HTTP)',
                'Details': 'سایت بدون گواهی سرو می‌شود'}

    valid_to = snap.get('ssl_valid_to')
    if valid_to is None:
        # صفحه سالم است و https است ولی security_details برنگشته. این بیشتر در
        # نسخه‌های خیلی قدیمی Playwright یا پاسخ‌های cached رخ می‌دهد؛ به کاربر
        # می‌گوییم که باید دستی چک کند.
        return {'Status': 'نیاز به بررسی دستی: اطلاعات گواهی SSL دریافت نشد',
                'Details': 'در مرورگر، قفل آدرس‌بار را دستی باز کنید'}

    try:
        expire = datetime.datetime.fromtimestamp(float(valid_to))
    except Exception:
        return {'Status': 'سالم', 'Details': 'معتبر (بدون تاریخ محدود)'}

    days_left = (expire - datetime.datetime.now()).days
    issuer = snap.get('ssl_issuer') or ''
    protocol = snap.get('ssl_protocol') or ''
    tail = ''
    if issuer:
        tail = f' | صادرکننده: {qc.short(issuer, 50)}'
    if protocol:
        tail = f'{protocol}{tail}'

    if days_left < 0:
        return {'Status': 'خطا: گواهی SSL منقضی شده',
                'Details': f'{abs(days_left)} روز از انقضا گذشته{(" | " + tail) if tail else ""}'}
    if days_left <= qc.SSL_DAYS_WARN:
        return {'Status': 'نیاز به بررسی دستی: انقضای نزدیک گواهی SSL',
                'Details': f'تنها {days_left} روز باقی مانده{(" | " + tail) if tail else ""}'}
    return {'Status': 'سالم',
            'Details': f'{days_left} روز اعتبار{(" | " + tail) if tail else ""}'}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
