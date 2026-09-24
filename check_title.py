# -*- coding: utf-8 -*-
"""
check_title.py - بررسی تگ <title>
اجرای تنها:  python check_title.py
خروجی:       reports/title_report.csv

قانون‌ها:
  - اگر صفحه، صفحه واقعی سایت نباشد (چالش، محدودیت VPN، ریدایرکت مشکوک، خطای سرور ...)
    تایتل آن صفحه «سالم» حساب نمی‌شود → «بررسی نشد: ...»
  - خالی / خیلی کوتاه / کاراکتر خراب / متن به‌هم‌ریخته (mojibake) → خطا
  - کلمات پیش‌فرض و تستی (test, untitled, lorem ipsum, تست, دسته‌بندی نشده, ...) → خطا
  - «home» یا «index» فقط وقتی کل تایتل همین باشد خطاست (نه وقتی بخشی از یک عنوان واقعی است)
  - نداشتن هیچ حرف فارسی → خطا (سایت‌ها فارسی هستند)
"""
import re
import sys
import qa_core as qc

TOOL_ID = 'title'
CSV_NAME = 'title_report.csv'
FIELDS = ['URL', 'Title Text', 'Status']

MIN_LEN = 3
REQUIRE_PERSIAN = True

BAD_WORDS_EN = ['test', 'testing', 'untitled', 'lorem ipsum', 'just another wordpress site',
                'my wordpress blog', 'new page', 'sample page', 'hello world', 'undefined', 'null']
BAD_EXACT = ['home', 'index', 'index.html', 'index.php', 'home page', 'homepage', 'default',
             'document', 'wordpress', 'website', 'site', 'صفحه اصلی', 'خانه', 'عنوان']
BAD_WORDS_FA = ['تست', 'آزمایشی', 'دسته بندی نشده', 'دسته‌بندی نشده', 'یک سایت دیگر با وردپرس',
                'سلام دنیا', 'برگه نمونه', 'بدون عنوان', 'لورم ایپسوم']
FA_LETTER = '\u0600-\u06FF'


def validate(text, what='تایتل', min_len=MIN_LEN, require_persian=REQUIRE_PERSIAN,
             check_bad_words=True, check_exact=True):
    """اعتبارسنجی Title؛ پارامترها اجازه می‌دهند Description قوانین جدا داشته باشد."""
    t = qc.clean_text(text)
    if not t:
        return f'خطا: {what} خالی/ناموجود'
    if '\ufffd' in t:
        return 'خطا: کاراکتر خراب (�) در متن'
    if qc.mojibake_count(t) >= 2:
        return 'خطا: متن به‌هم‌ریخته (مشکل انکودینگ)'
    if len(t) < min_len:
        return f'خطا: {what} بسیار کوتاه ({len(t)} کاراکتر)'
    low = t.lower()
    n = qc.norm_fa(t)
    if check_exact and n.strip(' -|–—:') in [qc.norm_fa(x) for x in BAD_EXACT]:
        return f'خطا: {what} پیش‌فرض/نامناسب («{t}»)'
    if check_bad_words:
        for w in BAD_WORDS_EN:
            if re.search(r'(?<![a-z0-9])' + re.escape(w) + r'(?![a-z0-9])', low):
                return f'خطا: کلمه ممنوعه ({w})'
        for w in BAD_WORDS_FA:
            wn = qc.norm_fa(w)
            if re.search(rf'(?<![{FA_LETTER}]){re.escape(wn)}(?![{FA_LETTER}])', n):
                return f'خطا: کلمه ممنوعه ({w})'
    if require_persian and not qc.has_persian(t):
        return f'خطا: {what} فاقد حروف فارسی'
    return 'سالم'


def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    title = qc.clean_text(snap.get('title', ''))
    if gate:
        return {'Title Text': title or '-', 'Status': gate}
    status = validate(title)
    note = qc.redirect_note(snap)
    if status == 'سالم' and note:
        status = 'سالم' + note
    return {'Title Text': title or '-', 'Status': status}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
