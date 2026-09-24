# -*- coding: utf-8 -*-
"""
run_all.py - اجرای همه چک‌ها با هم
اجرا:  python run_all.py              (همه چک‌ها)
       python run_all.py title favicon (فقط چک‌های نام‌برده)

هر سایت فقط «یک بار» باز می‌شود و همه چک‌ها روی همان صفحه اجرا می‌شوند
(به‌جای ۶ بار باز کردن هر سایت → ترافیک کمتر، احتمال بلاک شدن کمتر، نتیجه یکسان بین چک‌ها).
"""
import sys
import qa_core as qc

if __name__ == '__main__':
    ids = [a for a in sys.argv[1:] if a in qc.ALL_TOOLS] or None
    sys.exit(qc.run_checks(qc.load_modules(ids)))
