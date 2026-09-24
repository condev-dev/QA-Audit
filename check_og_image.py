# -*- coding: utf-8 -*-
"""
check_og_image.py - بررسی تصویر اشتراک‌گذاری (og:image)
اجرای تنها:  python check_og_image.py
خروجی:       reports/og_image_report.csv

روش: فایل تصویر واقعا دانلود می‌شود (کد HTTP + نوع فایل + حجم غیرصفر + امضای بایت‌های تصویر).
روش قبلی (new Image() داخل صفحه) به خاطر CSP/hotlink خطای الکی می‌داد.
  - تگ ناموجود/خالی، 404، فایل خالی، HTML به‌جای تصویر → خطا
  - 403/قطعی شبکه هنگام دانلود → «نیاز به بررسی دستی» (ممکن است مشکل IP/VPN باشد نه سایت)
"""
import sys
import qa_core as qc

TOOL_ID = 'og_image'
CSV_NAME = 'og_image_report.csv'
FIELDS = ['URL', 'Image URL', 'Status']


def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    ogs = [u for u in (snap.get('og') or []) if u]
    img = ogs[0] if ogs else '-'
    if gate:
        return {'Image URL': img, 'Status': gate}
    if not ogs:
        return {'Image URL': '-', 'Status': 'خطا: تگ og:image وجود ندارد'}
    referer = snap.get('final_url') or snap['url']
    level, reason = qc.check_asset(ctx, img, referer)
    if level == 'ok':
        return {'Image URL': img, 'Status': f'سالم ({reason})'}
    if level == 'warn':
        return {'Image URL': img, 'Status': f'نیاز به بررسی دستی: {reason}'}
    return {'Image URL': img, 'Status': f'خطا: تصویر OG — {reason}'}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
