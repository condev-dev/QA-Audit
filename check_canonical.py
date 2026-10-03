# -*- coding: utf-8 -*-
"""
check_canonical.py - بررسی تگ <link rel="canonical">

قانون‌ها:
  - اگر صفحه اصلی سالم نیست → «بررسی نشد»
  - اگر تگ canonical وجود ندارد (یا href خالی) → خطا
  - اگر canonical به دامنه‌ی دیگری (غیرهم‌برند) اشاره می‌کند → «نیاز به بررسی دستی»
  - اگر canonical به مسیر دیگری از همان دامنه اشاره می‌کند که URL نهایی صفحه نیست
    → «نیاز به بررسی دستی: canonical به مسیر دیگر صفحه اشاره می‌کند»
    (مثلاً صفحه example.com/ ولی canonical = example.com/en/home — این معمولاً
    اشتباه تنظیم تمپلیت است و SEO را خراب می‌کند)
  - در غیر این صورت → سالم
"""
import re
import sys
from urllib.parse import urlsplit
import qa_core as qc

TOOL_ID = 'canonical'
CSV_NAME = 'canonical_report.csv'
FIELDS = ['URL', 'Canonical URL', 'Status']


def _norm_path(u):
    """مسیر را نرمال می‌کند تا / و /index و سایر فرم‌ها به یک شکل مقایسه شوند."""
    try:
        p = urlsplit(u).path or '/'
    except Exception:
        return '/'
    # حذف اسلش انتهایی به‌جز وقتی خود / تنهاست
    if p != '/' and p.endswith('/'):
        p = p[:-1]
    return p.lower()


def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    if gate:
        return {'Canonical URL': '-', 'Status': gate}

    canons = snap.get('canon') or []

    # اگر در لیست استخراج شده هیچ لینکی نبود
    if not canons:
        html = snap.get('html') or ''
        # بررسی سورس خام برای اینکه ببینیم آیا تگ وجود دارد ولی href ندارد
        if re.search(r'rel\s*=\s*["\']canonical["\']', html, re.I):
            return {'Canonical URL': '-',
                    'Status': 'خطا: تگ canonical وجود دارد اما href ندارد یا خالی است'}
        return {'Canonical URL': '-', 'Status': 'خطا: تگ canonical وجود ندارد'}

    req_host = qc.host_of(snap['url'])
    final_url = snap.get('final_url') or snap['url']
    final_path = _norm_path(final_url)

    last_err = ''
    last_url = canons[0]

    # بررسی تک تک تگ‌های کانونی پیدا شده در صفحه
    for u in canons:
        u = u.strip()

        # شرط اول: فرمت درست باشد
        if not u.lower().startswith(('http://', 'https://')):
            last_err = 'خطا: فرمت آدرس canonical نامعتبر است'
            last_url = u
            continue

        # شرط دوم: به دامنه دیگری اشاره نکند
        can_host = qc.host_of(u)
        if can_host and qc.reg_domain(req_host) != qc.reg_domain(can_host):
            last_err = f'نیاز به بررسی دستی: canonical به دامنه دیگر اشاره می‌کند ({can_host})'
            last_url = u
            continue

        # شرط سوم (جدید): مسیر canonical باید با مسیر صفحه‌ی نهایی یکی باشد.
        can_path = _norm_path(u)
        if can_path != final_path:
            last_err = (f'نیاز به بررسی دستی: canonical به مسیر دیگر صفحه اشاره می‌کند '
                        f'(صفحه: {final_path or "/"} ↔ canonical: {can_path or "/"})')
            last_url = u
            continue

        # اگر به اینجا رسید، این تگ کاملاً سالم و معتبر است
        return {'Canonical URL': u, 'Status': 'سالم'}

    # هیچ تگ سالمی پیدا نشد؛ آخرین خطای یافت‌شده را گزارش می‌دهیم
    return {'Canonical URL': last_url, 'Status': last_err}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
