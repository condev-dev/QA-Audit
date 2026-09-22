import sys

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright, TimeoutError
import csv
import re
import arabic_reshaper
from bidi.algorithm import get_display

def print_fa(text):
    reshaped = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped)
    print(bidi_text)

BAD_WORDS_EN = ['test', 'home', 'index', 'untitled']
BAD_WORDS_FA = ['تست', 'دسته بندی نشده', 'just a moment', 'attention required', 'access denied', 'یک لحظه']

def safe_csv(text):
    if text and str(text).startswith(('=', '+', '-', '@')): return "'" + str(text)
    return text

def validate_description(desc_text, status_code):
    if status_code == 403: return "خطا: مسدود (403)"
    elif status_code >= 400: return f"خطا: سرور ({status_code})"
    if not desc_text: return "خطا: خالی/ناموجود"
        
    desc_clean = str(desc_text).strip().replace('\n', ' ').replace('\r', '')
    desc_clean = re.sub(r'\s+', ' ', desc_clean)
    
    if '\ufffd' in desc_clean: return "خطا: کاراکتر خراب ()"
    if len(desc_clean) < 10: return "خطا: بسیار کوتاه"
        
    desc_lower = desc_clean.lower()
    for word in BAD_WORDS_EN:
        if re.search(r'\b' + re.escape(word) + r'\b', desc_lower):
            return f"خطا: کلمه ممنوعه ({word})"
            
    for word in BAD_WORDS_FA:
        if word in desc_lower:
            return f"خطا: کلمه ممنوعه ({word})"
            
    if not re.search(r'[\u0600-\u06FF]', desc_clean): return "خطا: فاقد حروف فارسی"
        
    return "سالم"

def block_heavy_resources(route):
    excluded_types = ["image", "media", "font", "stylesheet"]
    if route.request.resource_type in excluded_types: route.abort()
    else: route.continue_()

def check_descriptions_only():
    try:
        with open('urls.txt', 'r', encoding='utf-8-sig') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print_fa("فایل urls.txt پیدا نشد!")
        return

    report_file = 'description_report.csv'
    with open(report_file, 'w', newline='', encoding='utf-8-sig') as f:
        csv.DictWriter(f, fieldnames=["URL", "Description Text", "Status"]).writeheader()
        
    # انتقال متغیر به بیرون از حلقه برای جلوگیری از خطای UnboundLocalError در تایم‌اوت اول
    js_code = '''
    () => {
        let meta = document.querySelector('meta[name="description" i]');
        return meta ? meta.content : "";
    }
    '''

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7"}
        )

        for url in urls:
            if not url.startswith('http'): url = 'https://' + url
            print_fa(f"در حال بررسی دیسکریپشن: {url} ...")
            
            page = context.new_page()
            page.route("**/*", block_heavy_resources)
            
            result = {"URL": url, "Description Text": "-", "Status": ""}
            
            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                status_code = response.status if response else 200
                actual_desc = page.evaluate(js_code)
                
                status_msg = validate_description(actual_desc, status_code)
                if status_code >= 400: actual_desc = "-"
                
                result["Description Text"] = safe_csv(actual_desc)
                result["Status"] = status_msg
                
            except TimeoutError:
                result["Status"] = "نیاز به بررسی دستی (تایم‌اوت)"
            except Exception as e:
                result["Status"] = f"خطا: عدم دسترسی ({str(e).split()[0][:30]})"
            finally:
                page.close()
                
            with open(report_file, 'a', newline='', encoding='utf-8-sig') as f:
                csv.DictWriter(f, fieldnames=["URL", "Description Text", "Status"]).writerow(result)

        browser.close()

    print_fa(f"\nبررسی تمام شد! فایل {report_file} را باز کن.")

if __name__ == "__main__":
    check_descriptions_only()
