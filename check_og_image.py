# -*- coding: utf-8 -*-
"""
check_og_image.py - بررسی تصویر اشتراک‌گذاری (og:image)
اجرای تنها:  python check_og_image.py
خروجی:       reports/og_image_report.csv

روش: فایل تصویر واقعا دانلود می‌شود (کد HTTP + نوع فایل + حجم غیرصفر + امضای بایت‌های تصویر).
روش قبلی (new Image() داخل صفحه) به خاطر CSP/hotlink خطای الکی می‌داد.

قواعد (مهم):
  - اگر صفحه چند تگ og:image داشته باشد، همه به ترتیب بررسی می‌شوند و
    به‌محض رسیدن به یک تصویر سالم، «سالم» اعلام می‌شود (نه فقط تگ اول).
    اگر تگ اول خراب بود ولی تگ دیگری سالم بود، در توضیح نوشته می‌شود.
  - اگر صفحه هیچ تگ og نداشته باشد (مثل صفحه اسکریپت اصلی کارفرما) ایراد محسوب نمی‌شود.
  - اگر صفحه تگ og دارد ولی og:image ندارد → خطا (طبق قاعده کارفرما).
  - 404 / فایل خالی / HTML به‌جای تصویر → خطا
  - 403 / قطعی شبکه هنگام دانلود → «نیاز به بررسی دستی» (ممکن است مشکل IP/VPN باشد نه سایت)
"""
import sys
import time
import qa_core as qc

TOOL_ID = 'og_image'
CSV_NAME = 'og_image_report.csv'
FIELDS = ['URL', 'Image URL', 'Status']
MAX_TRY = 6   # سقف تعداد تگ‌های بررسی‌شده و سقف زمان در qc.ASSET_BUDGET_S کنترل می‌شود


def _candidates(snap):
    """og:image ها اول، بعد og:image:secure_url / og:image:url — بدون تکرار."""
    out, seen = [], set()
    for u in (snap.get('og') or []):
        u = (u or '').strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    cands = _candidates(snap)
    img = cands[0] if cands else '-'
    if gate:
        return {'Image URL': img, 'Status': gate}
    if not cands:
        if int(snap.get('ogtags') or 0):
            return {'Image URL': '-',
                    'Status': 'خطا: صفحه تگ og دارد ولی og:image ندارد'}
        return {'Image URL': '-',
                'Status': 'سالم — صفحه هیچ تگ og ندارد (طبق قاعده کارفرما گزارش نمی‌شود)'}

    referer = snap.get('final_url') or snap['url']
    deadline = time.time() + qc.ASSET_BUDGET_S
    results = []
    for u in cands[:MAX_TRY]:
        level, reason = qc.check_asset(ctx, u, referer)
        results.append((u, level, reason))
        if level == 'ok':
            if u == cands[0]:
                return {'Image URL': u, 'Status': f'سالم ({reason})'}
            return {'Image URL': u,
                    'Status': f'سالم ({reason}) — تصویر اول خراب بود: {results[0][2]}'}
        if time.time() > deadline:
            break

    u0, _, r0 = results[0]
    if all(lv == 'warn' for _, lv, _ in results):
        return {'Image URL': u0, 'Status': f'نیاز به بررسی دستی: {r0}'}
    return {'Image URL': u0, 'Status': f'خطا: تصویر OG — {r0}'}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
