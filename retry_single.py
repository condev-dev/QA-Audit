import sys
import csv
import os
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin

if len(sys.argv) < 2:
    sys.exit()

url = sys.argv[1]
if not url.startswith('http'): url = 'https://' + url

def safe_csv(t): return "'" + str(t) if str(t).startswith(('=','+','-','@')) else t

def append_csv(file, fields, row):
    os.makedirs('reports', exist_ok=True)
    file_path = os.path.join('reports', file)
    exists = os.path.exists(file_path)
    with open(file_path, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        w.writerow(row)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(ignore_https_errors=True)
    page = ctx.new_page()
    page.route("**/*", lambda r: r.abort() if r.request.resource_type in ["media", "font"] else r.continue_())
    
    status, title_text, desc_text, og_img, fav_url, source_ok = "", "-", "-", "-", "-", "سالم"
    try:
        res = page.goto(url, wait_until='domcontentloaded', timeout=45000)
        code = res.status if res else 200
        if code >= 400 or 'just a moment' in page.title().lower():
            status = "خطا: مسدود/ارور"
        else:
            status = "سالم"
            title_text = page.title()
            
            desc_meta = page.query_selector('meta[name="description"]')
            desc_text = desc_meta.get_attribute('content') if desc_meta else "-"
            
            og_meta = page.evaluate('''() => { let m = document.querySelector('meta[property="og:image" i], meta[name="og:image" i]'); return m ? m.content : null; }''')
            og_img = urljoin(url, og_meta) if og_meta else "-"
            
            f_url = page.evaluate('''() => { let i = document.querySelector('link[rel~="icon"], link[rel="shortcut icon"]'); return i ? i.href : null; }''')
            fav_url = f_url if f_url else urljoin(url, '/favicon.ico')
            
            if '' in page.content(): source_ok = "خطا: کاراکتر مخدوش"
            
    except Exception as e:
        status = "خطا: تایم‌اوت / قطعی"
    finally:
        page.close()
        browser.close()

append_csv('title_report.csv', ["URL", "Title Text", "Length", "Status"], {"URL": url, "Title Text": safe_csv(title_text), "Length": len(title_text), "Status": status})
append_csv('description_report.csv', ["URL", "Description Text", "Length", "Status"], {"URL": url, "Description Text": safe_csv(desc_text), "Length": len(desc_text), "Status": status})
append_csv('og_image_report.csv', ["URL", "Image URL", "Status"], {"URL": url, "Image URL": safe_csv(og_img), "Status": status if og_img != "-" else "خطا: تگ ناموجود"})
append_csv('source_encoding_report.csv', ["URL", "Status"], {"URL": url, "Status": source_ok if status == "سالم" else status})
append_csv('favicon_report.csv', ["URL", "Favicon URL", "Status"], {"URL": url, "Favicon URL": safe_csv(fav_url), "Status": status})
