# -*- coding: utf-8 -*-
"""
check_source_encoding.py - بررسی کاراکترهای خراب سورس
اجرای تنها:  python check_source_encoding.py
خروجی:       reports/source_encoding_report.csv

سه بررسی:
  1) کاراکتر � (U+FFFD) در سورس رندرشده صفحه
  2) متن به‌هم‌ریخته (mojibake) مثل «Ø³Ù„Ø§Ù…» در متن قابل‌مشاهده، تایتل و دیسکریپشن
  3) بایت‌های نامعتبر UTF-8 در سورس خام سرور (وقتی صفحه UTF-8 اعلام شده)
"""
import re
import sys
import qa_core as qc

TOOL_ID = 'source_encoding'
CSV_NAME = 'source_encoding_report.csv'
FIELDS = ['URL', 'Status', 'Details']
MOJIBAKE_MIN = 3


def _context(s, idx, n=30):
    return qc.clean_text(s[max(0, idx - n): idx + n]).replace('\ufffd', '�')


def _raw_invalid_utf8(snap):
    raw = snap.get('raw')
    if not raw:
        return None
    ctype = (snap.get('content_type') or '').lower()
    m = re.search(r'charset=([\w-]+)', ctype)
    declared = (m.group(1) if m else (snap.get('charset') or '')).lower()
    if declared and declared not in ('utf-8', 'utf8'):
        return None
    txt = raw.decode('utf-8', errors='replace')
    return txt.count('\ufffd')


def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    if gate:
        return {'Status': gate, 'Details': '-'}
    html = snap.get('html') or ''
    visible = ' '.join([snap.get('title', ''), ' '.join(snap.get('descs') or []), snap.get('text', '')])

    n_fffd = html.count('\ufffd')
    if n_fffd:
        return {'Status': f'خطا: کاراکتر خراب (�) در سورس — {n_fffd} مورد',
                'Details': 'نمونه: ' + _context(html, html.index('\ufffd'))}

    n_moji = qc.mojibake_count(visible)
    if n_moji >= MOJIBAKE_MIN:
        m = qc.MOJIBAKE_RE.search(visible)
        return {'Status': f'خطا: متن به‌هم‌ریخته (mojibake) — {n_moji} مورد',
                'Details': 'نمونه: ' + _context(visible, m.start())}

    bad_raw = _raw_invalid_utf8(snap)
    if bad_raw:
        return {'Status': f'خطا: بایت نامعتبر UTF-8 در سورس خام — {bad_raw} مورد',
                'Details': f"charset: {snap.get('charset') or '-'}"}

    details = f"charset: {snap.get('charset') or '-'}"
    if bad_raw is None:
        return {'Status': 'نیاز به بررسی دستی: سورس خام دریافت نشد؛ فقط DOM بررسی شد',
                'Details': details}
    return {'Status': 'سالم — بدون کاراکتر خراب', 'Details': details}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
