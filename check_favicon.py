import sys

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright, TimeoutError
from urllib.parse import urljoin
import csv
import arabic_reshaper
from bidi.algorithm import get_display

def print_fa(text):
    bidi_text = get_display(arabic_reshaper.reshape(text))
    print(bidi_text)

BAD_WORDS = ['just a moment', 'attention required', 'access denied', 'یک لحظه']

def is_blocked_page(status_code, title_text):
    if status_code >= 400: return True
    if title_text:
        for word in BAD_WORDS:
            if word in title_text.lower(): return True
    return False

def safe_csv(text):
    if text and str(text).startswith(('=', '+', '-', '@')): return "'" + str(text)
    return text

def block_heavy_resources(route):
    excluded_types = ["image", "media", "font", "stylesheet"]
    if route.request.resource_type in excluded_types: route.abort()
    else: route.continue_()

def check_favicons_only():
    try:
        with open('urls.txt', 'r', encoding='utf-8-sig') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print_fa("فایل urls.txt پیدا نشد!")
        return

    report_file = 'favicon_report.csv'
    with open(report_file, 'w', newline='', encoding='utf-8-sig') as f:
        csv.DictWriter(f, fieldnames=["URL", "Favicon URL", "Status"]).writeheader()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 720}
        )

        for url in urls:
            if not url.startswith('http'): url = 'https://' + url
            print_fa(f"در حال استخراج لینک فوآیکون: {url} ...")
            
            page = context.new_page()
            page.route("**/*", block_heavy_resources)
            result = {"URL": url, "Favicon URL": "-", "Status": ""}
            
            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=60000)
                status_code = response.status if response else 200
                
                if is_blocked_page(status_code, page.title()):
                    result["Status"] = "خطا: مسدود (کلودفلر/سرور)"
                else:
                    # استخراج لیست تمام آیکون‌های موجود در صفحه + مسیر پیش‌فرض
                    fav_urls = page.evaluate('''() => {
                        let links = document.querySelectorAll('link[rel~="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]');
                        let urls = Array.from(links).map(link => link.href);
                        urls.push(window.location.origin + '/favicon.ico');
                        // حذف لینک‌های تکراری و خالی
                        return [...new Set(urls.filter(u => u))];
                    }''')
                    
                    page.unroute("**/*")
                    
                    working_url = None
                    last_error = "خطا: پیدا نشد (404/مخدوش)"
                    
                    # حلقه تست: پیدا کردن اولین آیکونی که واقعا لود می‌شود
                    for f_url in fav_urls:
                        if not f_url.startswith('http'):
                            f_url = urljoin(page.url, f_url)
                            
                        img_status = page.evaluate('''async (imgUrl) => {
                            return new Promise((resolve) => {
                                let img = new Image();
                                img.onload = () => resolve("سالم");
                                img.onerror = () => resolve("خطا: پیدا نشد (404/مخدوش)");
                                img.src = imgUrl;
                            });
                        }''', f_url)
                        
                        if img_status == "سالم":
                            working_url = f_url
                            break
                        else:
                            last_error = img_status
                    
                    if working_url:
                        result["Favicon URL"] = safe_csv(working_url)
                        result["Status"] = "سالم"
                    else:
                        # اگر هیچ‌کدام لود نشدند، اولین آدرس را برای گزارش قرار می‌دهد
                        result["Favicon URL"] = safe_csv(fav_urls[0] if fav_urls else "-")
                        result["Status"] = last_error
                        
            except TimeoutError:
                result["Status"] = "خطا: تایم‌اوت سایت"
            except Exception as e:
                err_str = str(e).lower()
                if "net::" in err_str:
                    result["Status"] = "خطا: قطعی شبکه/VPN"
                else:
                    result["Status"] = "خطا: باز نشد"
            finally:
                page.close()

            with open(report_file, 'a', newline='', encoding='utf-8-sig') as f:
                csv.DictWriter(f, fieldnames=["URL", "Favicon URL", "Status"]).writerow(result)

        browser.close()
        
    print_fa(f"\nاستخراج تمام شد! فایل {report_file} را باز کن.")

if __name__ == "__main__":
    check_favicons_only()
