# -*- coding: utf-8 -*-
"""
run_all.py - اجرای همه چک‌ها با هم
اجرا:  python run_all.py              (همه چک‌ها، CSVها از صفر)
       python run_all.py title favicon (فقط چک‌های نام‌برده)
       python run_all.py --resume      (ادامه اسکن قبلی: فقط سایت‌های
                                        باقی‌مانده که در health_report.csv نیستند)

هر سایت فقط «یک بار» باز می‌شود و همه چک‌ها روی همان صفحه اجرا می‌شوند
(به‌جای ۶ بار باز کردن هر سایت → ترافیک کمتر، احتمال بلاک شدن کمتر، نتیجه یکسان بین چک‌ها).
"""
import os
import sys
import csv
import qa_core as qc


def remaining_urls():
    """لیست سایت‌هایی که در urls.txt هستند ولی هنوز در health_report.csv ثبت نشده‌اند.

    مبنای تشخیص «بررسی شده» ستون URL در فایل سلامت است (health چک اصلی و اولین چک
    است و در هر اجرا برای همه سایت‌ها نوشته می‌شود). این منطق «stateless» است:
    هر چند بار استپ-ادامه کرده باشید، هر سایت که در CSV نیست باقی‌مانده حساب می‌شود.
    """
    all_urls = qc.load_urls()
    done = set()
    health_path = os.path.join(qc.REPORTS_DIR, 'health_report.csv')
    if os.path.exists(health_path):
        try:
            with open(health_path, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    k = qc.normalize_url((row or {}).get('URL', ''))
                    if k:
                        done.add(k)
        except Exception:
            pass
    return [u for u in all_urls if u not in done]


if __name__ == '__main__':
    args = sys.argv[1:]
    resume = '--resume' in args
    args = [a for a in args if a != '--resume']
    ids = [a for a in args if a in qc.ALL_TOOLS] or None

    if resume:
        urls = remaining_urls()
        if not urls:
            qc.setup_console()
            qc.log('چیزی برای ادامه نیست؛ همه سایت‌ها قبلا بررسی شده‌اند.')
            # progress را به حالت تمام‌شده بنویس تا UI به‌روز شود
            qc.write_progress({'state': 'done', 'tools': ids or qc.ALL_TOOLS,
                               'total': 0, 'done': 0, 'current_url': '',
                               'phase': '', 'started_at': qc._now(),
                               'finished_at': qc._now(),
                               'message': 'چیزی برای ادامه نبود؛ همه سایت‌ها قبلا بررسی شده‌اند.',
                               'counts': {'ok': 0, 'err': 0, 'warn': 0, 'skip': 0},
                               'resume': True})
            sys.exit(0)
        sys.exit(qc.run_checks(qc.load_modules(ids), urls=urls, append=True))

    sys.exit(qc.run_checks(qc.load_modules(ids)))
