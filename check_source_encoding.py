import sys

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright, TimeoutError
import csv
import arabic_reshaper
from bidi.algorithm import get_display

def print_fa(text):
    reshaped = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped)
    print(bidi_text)

BAD_CHAR_UNICODE = '\ufffd'
VPN_BLOCK_WORDS = ['just a moment', 'attention required', 'access denied', 'یک لحظه']

def is_blocked_page(status_code, title_text):
    if status_code == 403: return "خطا: مسدود (403)"
    elif status_code >= 400: return f"خطا: سرور ({status_code})"
    if title_text:
        title_lower = title_text.lower()
        for word in VPN_BLOCK_WORDS:
            if word in title_lower: return "خطا: کپچا/کلودفلر"
    return None

def block_heavy_resources(route):
    excluded_types = ["image", "media", "font", "stylesheet"]
    if route.request.resource_type in excluded_types: route.abort()
    else: route.continue_()

def check_entire_source_for_encoding():
    try:
        with open('urls.txt', 'r', encoding='utf-8-sig') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print_fa("فایل urls.txt پیدا نشد!")
        return

    report_file = 'source_encoding_report.csv'
    with open(report_file, 'w', newline='', encoding='utf-8-sig') as f:
        csv.DictWriter(f, fieldnames=["URL", "Status"]).writeheader()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7"},
            ignore_https_errors=True
        )

        for url in urls:
            if not url.startswith('http'): url = 'https://' + url
            print_fa(f"در حال اسکن سورس: {url} ...")
            
            page = context.new_page()
            page.route("**/*", block_heavy_resources)
            
            result = {"URL": url, "Status": ""}
            
            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                status_code = response.status if response else 200
                
                blocked_msg = is_blocked_page(status_code, page.title())
                
                if blocked_msg:
                    result["Status"] = blocked_msg
                else:
                    html_content = page.content()
                    if BAD_CHAR_UNICODE in html_content:
                        result["Status"] = "خطا: یافت شد ()"
                    else:
                        result["Status"] = "بدون کاراکتر خراب"
                        
            except TimeoutError:
                result["Status"] = "نیاز به بررسی دستی (تایم‌اوت)"
            except Exception as e:
                error_details = str(e).split('\n')[0][:40]
                result["Status"] = f"خطا: باز نشد ({error_details})"
            finally:
                page.close()

            with open(report_file, 'a', newline='', encoding='utf-8-sig') as f:
                csv.DictWriter(f, fieldnames=["URL", "Status"]).writerow(result)

        browser.close()
        
    print_fa(f"\nاسکن تمام شد! فایل {report_file} را باز کن.")

if __name__ == "__main__":
    check_entire_source_for_encoding()
