# -*- coding: utf-8 -*-
import sys
import datetime
import threading
import qa_core as qc

TOOL_ID = 'ssl'
CSV_NAME = 'ssl_report.csv'
# سوتی اینجا بود: SSL Status رو به Status تغییر دادم
FIELDS = ['URL', 'Status', 'Details']

class SSLChecker(threading.Thread):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.result = None

    def run(self):
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(ignore_https_errors=True)
                    page = context.new_page()
                    
                    response = page.goto(self.url, timeout=15000, wait_until='commit')
                    
                    if not response:
                        self.result = {'Status': 'بررسی نشد: خطا', 'Details': 'پاسخی از سمت سرور دریافت نشد'}
                        return
                        
                    sec = response.security_details() if callable(response.security_details) else response.security_details
                    
                    if not sec:
                        if self.url.startswith('http://'):
                            self.result = {'Status': 'خطا: نامعتبر (Not Secure)', 'Details': 'اتصال فاقد SSL (پروتکل HTTP)'}
                        else:
                            self.result = {'Status': 'بررسی نشد: خطا', 'Details': 'اطلاعات گواهینامه یافت نشد'}
                        return
                        
                    valid_to = sec.get('validTo') or sec.get('valid_to')
                    
                    if not valid_to:
                        self.result = {'Status': 'سالم', 'Details': 'معتبر (بدون تاریخ محدود)'}
                        return
                        
                    expire_date = datetime.datetime.fromtimestamp(valid_to)
                    days_left = (expire_date - datetime.datetime.now()).days
                    
                    if days_left < 0:
                        self.result = {'Status': 'خطا: منقضی شده', 'Details': f'{abs(days_left)} روز از انقضا گذشته'}
                    elif days_left <= 7:
                        self.result = {'Status': 'نیاز به بررسی دستی: انقضای نزدیک', 'Details': f'تنها {days_left} روز باقی‌مانده'}
                    else:
                        self.result = {'Status': 'سالم', 'Details': f'{days_left} روز اعتبار'}
                        
                finally:
                    browser.close()
        except Exception as e:
            err_msg = str(e)
            if "ERR_CERT" in err_msg:
                self.result = {'Status': 'خطا: نامعتبر (Not Secure)', 'Details': 'گواهینامه ناشناس یا نامعتبر است'}
            else:
                self.result = {'Status': 'بررسی نشد: خطا', 'Details': f'دلیل: {err_msg[:40]}'}

def analyze(ctx, snap):
    url = snap.get('url')
    if not url:
        return {'Status': '-', 'Details': 'آدرس نامعتبر'}
        
    if not url.startswith('http'):
        url = 'https://' + url
        
    checker = SSLChecker(url)
    checker.start()
    checker.join()
    
    return checker.result or {'Status': 'بررسی نشد: خطا', 'Details': 'خطای ناشناخته در پردازش'}

if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
