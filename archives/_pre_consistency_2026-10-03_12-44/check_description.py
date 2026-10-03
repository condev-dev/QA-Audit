# -*- coding: utf-8 -*-
"""
check_description.py - بررسی <meta name="description">
اجرای تنها:  python check_description.py
خروجی:       reports/description_report.csv

قانون‌ها:
  - صفحه غیرواقعی (چالش/محدودیت/ریدایرکت مشکوک/خطا) → «بررسی نشد: ...» (هرگز سالم الکی نمی‌شود)
  - تگ ناموجود یا خالی → خطا
  - کمتر از ۱۰ کاراکتر، کاراکتر خراب، متن به‌هم‌ریخته، کلمات تستی، بدون حرف فارسی → خطا
  - اگر چند تگ description با متن متفاوت باشد → «نیاز به بررسی دستی»
"""
import sys
import qa_core as qc
import check_title

TOOL_ID = 'description'
CSV_NAME = 'description_report.csv'
FIELDS = ['URL', 'Description Text', 'Status']

MIN_LEN = 10


def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    descs = [qc.clean_text(d) for d in (snap.get('descs') or [])]
    first = next((d for d in descs if d), '')
    if gate:
        return {'Description Text': first or '-', 'Status': gate}
    if not descs:
        return {'Description Text': '-', 'Status': 'خطا: تگ description وجود ندارد'}
    if not first:
        return {'Description Text': '-', 'Status': 'خطا: تگ description خالی است'}
    # Description متن طبیعی‌تری است؛ کلمات «تست»، «سایت» یا «خانه» در آن
    # به‌تنهایی ایراد نیستند و نباید با فهرست ممنوعه Title رد شوند.
    status = check_title.validate(first, what='توضیحات', min_len=MIN_LEN,
                                  check_bad_words=False, check_exact=False)
    distinct = {d for d in descs if d}
    if status == 'سالم' and len(distinct) > 1:
        return {'Description Text': first,
                'Status': f'نیاز به بررسی دستی: {len(distinct)} تگ description متفاوت در صفحه'}
    note = qc.redirect_note(snap)
    if status == 'سالم' and note:
        status = 'سالم' + note
    return {'Description Text': first, 'Status': status}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
