# -*- coding: utf-8 -*-
"""
check_health.py - سلامت سرور/صفحه اصلی
اجرای تنها:  python check_health.py
خروجی:       reports/health_report.csv

چه چیزهایی تشخیص داده می‌شود:
  DNS / اتصال رد شده / SSL نامعتبر / ریدایرکت بی‌پایان / تایم‌اوت سرور
  کدهای HTTP (4xx, 5xx, کلودفلر 520-527)
  صفحه سفید، خطای دیتابیس/PHP، صفحه پارک/پیش‌فرض هاست، Soft 404
  صفحه جایگزین: چالش Cloudflare، محدودیت IP/VPN/کشور، «به آدرس جدید بروید»،
  ریدایرکت به دامنه غیرهم‌برند، صفحه فیلترینگ (قطع بودن VPN خود ما)
"""
import sys
import qa_core as qc

TOOL_ID = 'health'
CSV_NAME = 'health_report.csv'
FIELDS = ['URL', 'Status', 'Details', 'Final URL']


def analyze(ctx, snap):
    v = snap['verdict']
    return {
        'Status': v['status'],
        'Details': v['details'],
        'Final URL': snap.get('final_url') or '-',
    }


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
