import sys

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright, TimeoutError
from urllib.parse import urljoin
import csv
import arabic_reshaper
from bidi.algorithm import get_display

def print_fa(text):
    reshaped = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped)
    print(bidi_text)

BAD_WORDS = ['just a moment', 'attention required', 'access denied', 'یک لحظه']

def is_blocked_page(status_code, title_text):
    if status_code >= 400: return True
    if title_text:
        title_lower = title_text.lower()
        for word in BAD_WORDS:
            if word in title_lower: return True
    return False

def block_heavy_resources(route):
    excluded_types = ["image", "media", "font", "stylesheet"]
    if route.request.resource_type in excluded_types: route.abort()
    else: route.continue_()

def safe_csv(text):
    if text and str(text).startswith(('=', '+', '-', '@')): return "'" + str(text)
    return text

def extract_og_images():
    try:
        with open('urls.txt', 'r', encoding='utf-8-sig') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        print_fa("فایل urls.txt پیدا نشد!")
        return

    report_file = 'og_image_report.csv'
    with open(report_file, 'w', newline='', encoding='utf-8-sig') as f:
        csv.DictWriter(f, fieldnames=["URL", "Image URL", "Status"]).writeheader()
    
    js_code = '''
    () => {
        let meta = document.querySelector('meta[property="og:image" i]') || document.querySelector('meta[name="og:image" i]');
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
            print_fa(f"در حال استخراج عکس: {url} ...")
            
            page = context.new_page()
            page.route("**/*", block_heavy_resources)
            
            result = {"URL": url, "Image URL": "-", "Status": ""}
            
            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                status_code = response.status if response else 200
                page_title = page.title()
                
                if is_blocked_page(status_code, page_title):
                    result["Status"] = "خطا"
                    result["Image URL"] = "مسدود یا ارور سرور"
                else:
                    og_image = page.evaluate(js_code)
                    if og_image and str(og_image).strip():
                        full_image_url = urljoin(page.url, str(og_image).strip())
                        result["Image URL"] = safe_csv(full_image_url)
                        result["Status"] = "سالم"
                    else:
                        result["Status"] = "خطا"
                        result["Image URL"] = "تگ خالی یا ناموجود"
                        
            except TimeoutError:
                result["Status"] = "خطا"
                result["Image URL"] = "تایم‌اوت (نیاز به بررسی دستی)"
            except Exception as e:
                result["Status"] = "خطا"
                result["Image URL"] = f"عدم دسترسی ({str(e).split()[0][:30]})"
            finally:
                page.close()

            with open(report_file, 'a', newline='', encoding='utf-8-sig') as f:
                csv.DictWriter(f, fieldnames=["URL", "Image URL", "Status"]).writerow(result)

        browser.close()

    print_fa(f"\nبررسی تمام شد! فایل {report_file} را باز کن.")

if __name__ == "__main__":
    extract_og_images()
