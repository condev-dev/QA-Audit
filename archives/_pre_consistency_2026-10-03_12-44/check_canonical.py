# -*- coding: utf-8 -*-
import re
import sys
import qa_core as qc

TOOL_ID = 'canonical'
CSV_NAME = 'canonical_report.csv'
FIELDS = ['URL', 'Canonical URL', 'Status']

def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    if gate:
        return {'Canonical URL': '-', 'Status': gate}
        
    canons = snap.get('canon') or []
    
    # اگر در لیست استخراج شده هیچ لینکی نبود
    if not canons:
        html = snap.get('html') or ''
        # بررسی سورس خام برای اینکه ببینیم آیا تگ وجود دارد ولی href ندارد
        if re.search(r'rel\s*=\s*["\']canonical["\']', html, re.I):
            return {'Canonical URL': '-', 'Status': 'خطا: تگ canonical وجود دارد اما مقدار href ندارد یا خالی است'}
        return {'Canonical URL': '-', 'Status': 'خطا: تگ canonical وجود ندارد'}
        
    req_host = qc.host_of(snap['url'])
    
    last_err = ''
    last_url = canons[0]
    
    # بررسی تک تک تگ‌های کانونی پیدا شده در صفحه
    for u in canons:
        u = u.strip()
        
        # شرط اول: فرمت درست باشد
        if not u.lower().startswith(('http://', 'https://')):
            last_err = 'خطا: فرمت آدرس canonical نامعتبر است'
            last_url = u
            continue
            
        # شرط دوم: به دامنه دیگری اشاره نکند
        can_host = qc.host_of(u)
        if can_host and qc.reg_domain(req_host) != qc.reg_domain(can_host):
            last_err = f'نیاز به بررسی دستی: اشاره به دامنه دیگر ({can_host})'
            last_url = u
            continue
            
        # اگر به اینجا رسید، یعنی این تگ کاملا سالم و معتبر است
        # به محض پیدا کردن اولین تگ سالم، کار تمام است و بقیه تگ‌ها مهم نیستند
        return {'Canonical URL': u, 'Status': 'سالم'}
        
    # اگر حلقه تمام شد و هیچ تگ سالمی پیدا نکرد، آخرین خطای یافت شده را گزارش می‌دهد
    return {'Canonical URL': last_url, 'Status': last_err}

if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
