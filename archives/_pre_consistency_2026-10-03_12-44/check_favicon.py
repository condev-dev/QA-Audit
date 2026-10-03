# -*- coding: utf-8 -*-
"""
check_favicon.py - بررسی فوآیکون
اجرای تنها:  python check_favicon.py
خروجی:       reports/favicon_report.csv

روش: آیکون‌های تعریف‌شده در صفحه (icon / shortcut icon / apple-touch-icon) به ترتیب
دانلود و بررسی می‌شوند؛ اگر هیچ‌کدام تعریف نشده بود /favicon.ico امتحان می‌شود.
  - اولین آیکون سالم → سالم
  - آیکون تعریف‌شده خراب ولی آیکون دیگری سالم → سالم با توضیح
  - هیچ آیکون سالمی نیست → خطا (یا «نیاز به بررسی دستی» اگر فقط به خاطر 403/شبکه دانلود نشد)
  - سقف زمان دانلود آیکون‌های هر سایت qc.ASSET_BUDGET_S است تا سایت خراب، اسکن را کند نکند.
"""
import sys
import time
from urllib.parse import urlsplit
import qa_core as qc

TOOL_ID = 'favicon'
CSV_NAME = 'favicon_report.csv'
FIELDS = ['URL', 'Favicon URL', 'Status']
MAX_TRY = 10  # همه لینک‌های متعارف صفحه را بررسی کن؛ تعدادشان معمولاً کم است.


def _candidates(snap):
    icons = snap.get('icons') or []
    first = [i['href'] for i in icons if 'apple' not in i.get('rel', '')]
    apple = [i['href'] for i in icons if 'apple' in i.get('rel', '')]
    out, seen = [], set()
    for u in first + apple:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    if gate:
        return {'Favicon URL': '-', 'Status': gate}
    base = snap.get('final_url') or snap['url']
    p = urlsplit(base)
    default_ico = f'{p.scheme}://{p.netloc}/favicon.ico'
    declared = _candidates(snap)
    tries = declared[:MAX_TRY] if declared else [default_ico]

    results = []
    # سقف زمان: اگر سایت تعداد زیادی آیکون خراب/کند داشته باشد، اسکن معطل نماند
    deadline = time.time() + qc.ASSET_BUDGET_S
    for u in tries:
        level, reason = qc.check_asset(ctx, u, base)
        results.append((u, level, reason))
        if level == 'ok':
            if not declared:
                return {'Favicon URL': u, 'Status': f'سالم (favicon.ico پیش‌فرض — {reason})'}
            if u != tries[0]:
                return {'Favicon URL': u, 'Status': f'سالم ({reason}) — آیکون اول خراب بود: {results[0][2]}'}
            return {'Favicon URL': u, 'Status': f'سالم ({reason})'}
        if time.time() > deadline:
            break

    u0, _, r0 = results[0]
    if any(lv == 'warn' for _, lv, _ in results) and not any(lv == 'err' for _, lv, _ in results):
        return {'Favicon URL': u0, 'Status': f'نیاز به بررسی دستی: {r0}'}
    if not declared:
        return {'Favicon URL': u0, 'Status': f'خطا: فوآیکون تعریف نشده و favicon.ico هم نیست ({r0})'}
    return {'Favicon URL': u0, 'Status': f'خطا: فوآیکون — {r0}'}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
