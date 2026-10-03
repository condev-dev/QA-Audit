# -*- coding: utf-8 -*-
"""
check_description.py - بررسی <meta name="description">
اجرای تنها:  python check_description.py
خروجی:       reports/description_report.csv

قانون‌ها:
  - صفحه غیرواقعی (چالش/محدودیت/ریدایرکت مشکوک/خطا) → «بررسی نشد: ...» (هرگز سالم الکی نمی‌شود)
  - تگ ناموجود یا خالی → خطا
  - کمتر از ۱۰ کاراکتر، کاراکتر خراب، متن به‌هم‌ریخته → خطا
  - بدون حرف فارسی → «نیاز به بررسی دستی» (هم‌خوان با title؛ قبلاً خطا بود و باعث
    ناسازگاری با تایتل روی سایت‌های عربی/انگلیسی می‌شد)
  - اگر چند تگ description با متن متفاوت باشد → «نیاز به بررسی دستی»
"""
import sys
import qa_core as qc
import check_title

TOOL_ID = 'description'
CSV_NAME = 'description_report.csv'
FIELDS = ['URL', 'Description Text', 'Status']

# از qa_core یکدست خوانده می‌شود؛ متغیر محلی فقط برای سازگاری عقب‌رو.
MIN_LEN = qc.DESC_MIN_LEN


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
    # persian_level='warn' تا هم‌خوان با تایتل عمل کند (قبلاً err بود).
    status = check_title.validate(first, what='توضیحات', min_len=MIN_LEN,
                                  check_bad_words=False, check_exact=False,
                                  persian_level='warn')
    distinct = {d for d in descs if d}
    if status == 'سالم' and len(distinct) > 1:
        return {'Description Text': first,
                'Status': f'نیاز به بررسی دستی: {len(distinct)} تگ description متفاوت در صفحه'}
    # redirect_note در qc.run_analyze به صورت یکدست روی همه چک‌ها اعمال می‌شود.
    return {'Description Text': first, 'Status': status}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
