# -*- coding: utf-8 -*-
"""
qa_core.py - هسته مشترک همه چک‌ها

هر چک در فایل جداگانه خودش است (check_*.py) و فقط منطق همان بخش را دارد.
این فایل کارهای مشترک را انجام می‌دهد تا همه چک‌ها دقیقا یک رفتار داشته باشند:
  - خواندن و یکسان‌سازی لینک‌ها (urls.txt)
  - باز کردن مرورگر شبیه کاربر واقعی (ضد تشخیص ربات)
  - لود صفحه با تلاش مجدد + تشخیص قطعی اینترنت/VPN (تا خطای الکی ثبت نشود)
  - تشخیص صفحه‌های جایگزین: فیلترینگ، چالش Cloudflare/Arvan، محدودیت IP/VPN،
    صفحه «به آدرس جدید بروید»، ریدایرکت به دامنه دیگر، صفحه پارک/پیش‌فرض، 404 نرم و ...
  - نوشتن CSV و فایل پیشرفت برای پنل

سطح وضعیت‌ها (پنل بر اساس شروع متن رنگ می‌دهد):
  «سالم ...»              → سبز
  «خطا: ...»              → قرمز   (مشکل واقعی سایت)
  «نیاز به بررسی دستی: ...» → نارنجی (مشکوک؛ باید با چشم دیده شود)
  «بررسی نشد: ...»         → خاکستری (به خاطر مشکل دیگر یا قطعی شبکه ما قابل بررسی نبود)
"""
import os
import sys
import re
import csv
import json
import time
import random
import traceback
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

# ----------------------------------------------------------------- مسیرها
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
URLS_FILE = os.path.join(BASE_DIR, 'urls.txt')
PROGRESS_FILE = os.path.join(REPORTS_DIR, '_progress.json')
STOP_FILE = os.path.join(REPORTS_DIR, '_stop')
os.makedirs(REPORTS_DIR, exist_ok=True)

# ترتیب اجرای چک‌ها. برای افزودن چک جدید: فایل check_<id>.py بسازید و id را اینجا اضافه کنید.
ALL_TOOLS = ['health', 'title', 'description', 'og_image', 'source_encoding', 'favicon', 'canonical', 'ssl']

# ----------------------------------------------------------------- تنظیمات
NAV_TIMEOUT_MS = 45000          # حداکثر زمان لود اولیه صفحه
IDLE_WAIT_MS = 8000             # صبر برای آرام شدن شبکه (اسکریپت‌ها/ریدایرکت‌های JS)
CHALLENGE_WAIT_S = 25           # صبر برای رد شدن خودکار چالش Cloudflare/Arvan
MAX_ATTEMPTS = 3                # تعداد تلاش برای هر سایت در خطاهای موقت
RETRY_STATUSES = {429, 500, 502, 503, 504, 520, 521, 522, 523, 524}
PAUSE_RANGE = (1.0, 2.5)        # مکث تصادفی بین سایت‌ها (رفتار انسانی، جلوگیری از بلاک)
HEADLESS = os.environ.get('QA_HEADLESS', '1') != '0'   # برای دیدن مرورگر: QA_HEADLESS=0
REDIRECT_SAME_BRAND_OK = os.environ.get('QA_SAME_BRAND_REDIRECT_OK', '1') != '0'
# ↑ پیش‌فرض دقیقا مثل قبل است (ریدایرکت به دامنه‌ی هم‌برند سالم حساب می‌شود).
#   اگر خواستی طبق بند ۵ سند کارفرما «ریدایرکت به دامنه‌ی دیگر» هم گزارش شود:
#   QA_SAME_BRAND_REDIRECT_OK=0

# این‌ها فقط برای تنظیم زمان بدون دست‌زدن به کد هستند (پیش‌فرض‌ها هیچ تغییری نکرده‌اند)
IDLE_WAIT_MS = int(os.environ.get('QA_IDLE_WAIT_MS') or IDLE_WAIT_MS)
NAV_TIMEOUT_MS = int(os.environ.get('QA_NAV_TIMEOUT_MS') or NAV_TIMEOUT_MS)
CHALLENGE_WAIT_S = int(os.environ.get('QA_CHALLENGE_WAIT_S') or CHALLENGE_WAIT_S)
# سقف زمان دانلود تصویرهای هر سایت (og/آیکون) تا یک سایت خراب، کل اسکن را کند نکند
ASSET_BUDGET_S = float(os.environ.get('QA_ASSET_BUDGET_S') or 30)
CONNECTIVITY_URLS = [
    'https://www.google.com/generate_204',
    'https://www.cloudflare.com/cdn-cgi/trace',
    'https://www.microsoft.com/favicon.ico',
]

# ----------------------------------------------------------------- کنسول
def setup_console():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_BIDI = True
except Exception:
    _HAS_BIDI = False


def log(text):
    t = str(text)
    if _HAS_BIDI and os.environ.get('QA_PLAIN_LOG') != '1':
        try:
            t = get_display(arabic_reshaper.reshape(t))
        except Exception:
            pass
    try:
        print(t, flush=True)
    except Exception:
        pass

# ----------------------------------------------------------------- لینک‌ها
def normalize_url(raw):
    """یک کلید یکسان برای هر سایت: https://host(/path) با host کوچک و بدون / انتهایی."""
    s = (raw or '').strip().lstrip('\ufeff').strip()
    if not s:
        return ''
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', s):
        s = 'https://' + s
    p = urlsplit(s)
    path = p.path if p.path not in ('', '/') else ''
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, p.query, ''))


def load_urls():
    if not os.path.exists(URLS_FILE):
        return []
    out, seen = [], set()
    with open(URLS_FILE, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            u = normalize_url(line)
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    return out


def host_of(url):
    try:
        h = (urlsplit(url).hostname or '').lower()
    except Exception:
        h = ''
    return h[4:] if h.startswith('www.') else h


def reg_domain(host):
    parts = [x for x in (host or '').split('.') if x]
    return '.'.join(parts[-2:]) if len(parts) >= 2 else (host or '')


def brand_of(host):
    return re.sub(r'[^a-z0-9]', '', reg_domain(host).split('.')[0])


def same_brand(h1, h2):
    a, b = brand_of(h1), brand_of(h2)
    if not a or not b:
        return False
    if a == b:
        return True
    short = min(a, b, key=len)
    return len(short) >= 4 and (a in b or b in a)

# ----------------------------------------------------------------- متن
PERSIAN_RE = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
MOJIBAKE_RE = re.compile(
    r'[\u00D8\u00D9\u00DA\u00DB][\u0080-\u00BF\u0152\u0153\u0160\u0161\u0178\u017D\u017E\u0192'
    r'\u02C6\u02DC\u2013\u2014\u2018-\u201E\u2020-\u2022\u2026\u2030\u2039\u203A\u20AC\u2122]'
    r'|\u00C3[\u0080-\u00BF]|\u00E2\u20AC'
)
_DIACRITICS_RE = re.compile(r'[\u064B-\u065F\u0670]')


def clean_text(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def norm_fa(s):
    s = str(s or '').lower()
    s = s.replace('\u064a', '\u06cc').replace('\u0643', '\u06a9')
    s = s.replace('\u200c', ' ').replace('\u200f', '').replace('\u200e', '')
    s = _DIACRITICS_RE.sub('', s)
    return re.sub(r'\s+', ' ', s).strip()


def has_persian(s):
    return bool(PERSIAN_RE.search(s or ''))


def mojibake_count(s):
    return len(MOJIBAKE_RE.findall(s or ''))


def safe_csv(v):
    """جلوگیری از اجرای فرمول هنگام باز کردن CSV در اکسل."""
    s = '' if v is None else str(v)
    if s and s[0] in ('=', '+', '@', '\t', '\r'):
        return "'" + s
    return s


def short(s, n=120):
    s = clean_text(s)
    return s if len(s) <= n else s[:n] + '…'

# ----------------------------------------------------------------- الگوهای تشخیص
CHALLENGE_TITLES = [
    'just a moment', 'attention required', 'checking your browser', 'please wait',
    'one moment', 'ddos-guard', 'security check', 'verify you are human',
    'verifying you are human', 'bot verification', 'captcha',
    'لطفا صبر کنید', 'لطفا منتظر بمانید', 'در حال بررسی مرورگر', 'بررسی امنیتی', 'یک لحظه',
]
CHALLENGE_HTML_STRONG = [
    '_cf_chl_opt', 'cf-browser-verification', 'cf_chl_prog', 'id="challenge-form"',
    'sucuri_cloudproxy_js', '/.well-known/sgcaptcha', 'ddos-guard.net/',
]
CHALLENGE_HTML_WEAK = [
    # این‌ها نشانه‌های فنی چالش هستند؛ «captcha» یا «arvancloud» به‌تنهایی
    # روی سایت سالم هم زیاد دیده می‌شوند و نباید باعث خطای تشخیص شوند.
    'challenges.cloudflare.com', '/cdn-cgi/challenge-platform',
    'cf-turnstile', 'turnstile.render', 'ddos-guard.net/',
]
BLOCK_TITLES = [
    'access denied', '403 forbidden', 'forbidden', 'error 1020', 'error 1009', 'error 1006',
    'error 1005', 'not available in your', 'ip banned', 'blocked',
    'دسترسی غیرمجاز', 'عدم دسترسی', 'دسترسی محدود', 'دسترسی مسدود',
]
GEO_WORDS = [
    # کلمات عمومی مثل VPN و IP حذف شده‌اند؛ این‌ها در محتوای عادی هم می‌آیند.
    'your ip address has been blocked', 'your ip is not allowed', 'ip has been banned',
    'not available in your country', 'not available in your region',
    'your country is not supported', 'your region is not supported', 'access restricted',
    'دسترسی شما مسدود است', 'آی پی شما مسدود است', 'آی‌پی شما مجاز نیست',
    'این کشور پشتیبانی نمی‌شود', 'این منطقه پشتیبانی نمی‌شود', 'خارج از ایران', 'خارج از کشور',
]
REDIRECT_WORDS = [
    # فقط عبارت‌های نسبتاً مشخص؛ «سایت جدید» یا «لینک جدید» به‌تنهایی طبیعی‌اند.
    'به آدرس جدید بروید', 'به دامنه جدید بروید', 'آدرس بدون فیلتر', 'منتقل شد',
    'منتقل شده', 'در حال انتقال', 'ورود به سایت اصلی', 'new address', 'new domain',
    'has moved', 'moved to', 'redirecting', 'you will be redirected',
    'click here to continue',
]
PARKED_WORDS = [
    'domain is for sale', 'this domain is for sale', 'buy this domain', 'domain may be for sale',
    'parkingcrew', 'sedoparking', 'account suspended', 'account has been suspended',
    'default web page', 'welcome to nginx', 'apache2 ubuntu default page',
    'apache2 debian default page', 'test page for the apache', 'there is no website configured',
    'website is under construction', 'under construction', 'coming soon', 'در دست ساخت',
]
# (?<!\d)404(?!\d) تا عدد سال شمسی مثل «1404» اشتباهی 404 حساب نشود
SOFT404_RE = re.compile(r'(?<!\d)404(?!\d)|not found|یافت نشد|پیدا نشد|وجود ندارد')
PHP_ERR_RE = re.compile(r'(fatal error|parse error|warning|notice|deprecated)\s*:.{0,300}?on line\s*\d+', re.I | re.S)
SERVER_ERR_WORDS = [
    'error establishing a database connection',
    'there has been a critical error on this website',
    'خطای مهمی در این وب سایت رخ داده',
    'sqlstate[',
]
CF_CODES = {
    520: 'پاسخ نامعتبر از سرور اصلی', 521: 'وب‌سرور خاموش است', 522: 'اتصال به سرور اصلی تایم‌اوت شد',
    523: 'سرور اصلی در دسترس نیست', 524: 'سرور اصلی دیر پاسخ داد', 525: 'خطای SSL سرور اصلی',
    526: 'گواهی SSL سرور اصلی نامعتبر', 527: 'خطای Railgun',
}


def _any(words, text):
    for w in words:
        if norm_fa(w) in text:
            return w
    return None

# ----------------------------------------------------------------- مرورگر
_INIT_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || {runtime: {}};
Object.defineProperty(navigator, 'languages', {get: () => ['fa-IR', 'fa', 'en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
"""


def open_browser(p):
    browser = p.chromium.launch(
        headless=HEADLESS,
        args=['--disable-blink-features=AutomationControlled', '--no-first-run',
              '--no-default-browser-check'],
    )
    try:
        major = browser.version.split('.')[0]
    except Exception:
        major = '124'
    ua = (f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          f'(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36')
    ctx = browser.new_context(
        user_agent=ua,
        locale='fa-IR',
        viewport={'width': 1366, 'height': 768},
        ignore_https_errors=False,   # گواهی خراب = مشکل واقعی سایت
        extra_http_headers={'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7'},
    )
    ctx.add_init_script(_INIT_JS)
    return browser, ctx


def _route_block(route):
    try:
        if route.request.resource_type in ('image', 'media', 'font'):
            route.abort()
        else:
            route.continue_()
    except Exception:
        pass


def _probe_ok(u, r):
    """پاسخ واقعی اینترنت است یا صفحه‌ی جایگزین (کپتیو پورتال / هشدار VPN)؟"""
    if r.status >= 500:
        return False
    try:
        body = r.body() or b''
    except Exception:
        body = b''
    head = body[:600].lstrip().lower()
    # جای پاسخ واقعی، یک صفحه‌ی HTML برگشته = اینترنت/VPN سالم نیست
    if head.startswith(b'<!doctype') or head.startswith(b'<html') or b'<html' in head[:200]:
        return False
    if 'cdn-cgi/trace' in u and body and b'ip=' not in body[:600]:
        return False
    return True


def internet_ok(ctx):
    for u in CONNECTIVITY_URLS:
        try:
            r = ctx.request.get(u, timeout=12000, max_redirects=3)
            ok = _probe_ok(u, r)
            try:
                r.dispose()
            except Exception:
                pass
            if ok:
                return True
        except Exception:
            continue
    return False


def wait_for_internet(ctx, max_wait=150):
    end = time.time() + max_wait
    while time.time() < end:
        if internet_ok(ctx):
            return True
        log('اینترنت/VPN قطع است؛ منتظر اتصال مجدد ...')
        time.sleep(10)
    return internet_ok(ctx)

# ----------------------------------------------------------------- لود صفحه
_COLLECT_JS = r"""
() => {
  const abs = (v) => { try { return new URL(v, document.baseURI).href } catch (e) { return v || '' } };
  const qa = (s) => Array.from(document.querySelectorAll(s));
  const descs = qa('meta[name="description" i]').map(m => m.getAttribute('content') || '');
  const og1 = qa('meta[property="og:image" i], meta[name="og:image" i]').map(m => (m.getAttribute('content') || '').trim()).filter(Boolean);
  const og2 = qa('meta[property="og:image:secure_url" i], meta[name="og:image:secure_url" i], meta[property="og:image:url" i], meta[name="og:image:url" i]').map(m => (m.getAttribute('content') || '').trim()).filter(Boolean);
  const canon = qa('link[rel="canonical" i][href]').map(l => (l.getAttribute('href') || '').trim()).filter(Boolean);
  const ogtags = qa('meta[property^="og:" i], meta[name^="og:" i]').length;
  const ogurl = qa('meta[property="og:url" i], meta[name="og:url" i]').map(m => (m.getAttribute('content') || '').trim()).filter(Boolean);
  const icons = qa('link[rel][href]')
    .filter(l => /(^|\s)(icon|apple-touch-icon|apple-touch-icon-precomposed)(\s|$)/i.test(l.getAttribute('rel') || ''))
    .map(l => ({rel: (l.getAttribute('rel') || '').toLowerCase().trim(), href: abs(l.getAttribute('href'))}));
  const mr = document.querySelector('meta[http-equiv="refresh" i]');
  const b = document.body;
  return {
    descs: descs, og: og1.concat(og2).map(abs), icons: icons,
    canon: canon.map(abs), ogurl: ogurl.map(abs), ogtags: ogtags,
    refresh: mr ? (mr.getAttribute('content') || '') : '',
    text: b ? (b.innerText || '') : '',
    elements: b ? b.getElementsByTagName('*').length : 0,
    charset: document.characterSet || ''
  };
}
"""

_EMPTY_INFO = {'title': '', 'html': '', 'descs': [], 'og': [], 'icons': [], 'refresh': '',
               'canon': [], 'ogurl': [], 'ogtags': 0, 'text': '', 'elements': 0, 'charset': ''}


def _collect(page):
    for _ in range(3):
        try:
            title = page.title()
            data = page.evaluate(_COLLECT_JS)
            html = page.content()
            data['title'] = title or ''
            data['html'] = html or ''
            return data
        except Exception:
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
    return dict(_EMPTY_INFO)


def _settle(page, ms=IDLE_WAIT_MS):
    try:
        page.wait_for_load_state('networkidle', timeout=ms)
    except Exception:
        pass
    try:
        page.wait_for_timeout(500)
    except Exception:
        pass


def _is_small(info, limit=400):
    return len(clean_text(info.get('text', ''))) < limit


def is_challenge(info):
    title = norm_fa(info.get('title', ''))
    html = (info.get('html') or '')[:300000].lower()
    if any(norm_fa(t) in title for t in CHALLENGE_TITLES):
        return True
    if any(m in html for m in CHALLENGE_HTML_STRONG):
        return True
    if _is_small(info) and any(m in html for m in CHALLENGE_HTML_WEAK):
        return True
    return False


def is_filter_page(info, final_url):
    html = (info.get('html') or '')[:300000].lower()
    return ('peyvandha' in (final_url or '').lower() or 'peyvandha.ir' in html
            or bool(re.search(r'10\.10\.34\.3[4-6]', html)))


def classify_error(msg):
    m = (msg or '').upper()
    code = re.search(r'NET::(ERR_[A-Z_]+)', m)
    code = code.group(1) if code else ''
    if 'ERR_NAME_NOT_RESOLVED' in m or 'NXDOMAIN' in m:
        return 'dns', code
    if 'ERR_CONNECTION_REFUSED' in m:
        return 'refused', code
    if 'ERR_CERT' in m:
        return 'cert', code
    if 'ERR_TOO_MANY_REDIRECTS' in m:
        return 'redirect_loop', code
    if 'ERR_CONNECTION_TIMED_OUT' in m or 'ERR_ADDRESS_UNREACHABLE' in m:
        return 'conn_timeout', code
    if 'ERR_SSL' in m or 'SSL_PROTOCOL' in m:
        return 'ssl_proto', code
    if any(x in m for x in ('ERR_CONNECTION_RESET', 'ERR_CONNECTION_CLOSED', 'ERR_EMPTY_RESPONSE',
                            'ERR_TUNNEL', 'ERR_PROXY', 'ERR_INTERNET_DISCONNECTED',
                            'ERR_NETWORK', 'ERR_TIMED_OUT', 'ERR_QUIC')):
        return 'network', code
    if 'TIMEOUT' in m:
        return 'timeout', code or 'Timeout'
    if 'ERR_ABORTED' in m:
        return 'aborted', code
    return 'other', code


def _new_snap(url):
    s = dict(_EMPTY_INFO)
    s.update({'url': url, 'loaded': False, 'final_url': '', 'status': None, 'content_type': '',
              'raw': None, 'load_s': None, 'attempts': 1, 'error_kind': None, 'error_code': '',
              'error_msg': '', 'slow': False, 'filter': False, 'challenge': False,
              'block_msg': '', 'page_error': '', 'foreign': ''})
    return s


def _load_once(ctx, url):
    snap = _new_snap(url)
    page = None
    t0 = time.time()
    try:
        page = ctx.new_page()
        page.route('**/*', _route_block)
        nav = {'resp': None}

        def on_response(r):
            try:
                if r.request.is_navigation_request() and r.frame == page.main_frame:
                    nav['resp'] = r
            except Exception:
                pass

        page.on('response', on_response)
        try:
            resp = page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
            if nav['resp'] is None and resp is not None:
                nav['resp'] = resp
        except Exception as e:
            kind, code = classify_error(str(e))
            # اگر فقط کند بود ولی محتوا آمده، همان را بررسی کن (سایت کند ≠ سایت خراب)
            if kind == 'timeout':
                info = _collect(page)
                if info.get('title') and len(info.get('html', '')) > 2000:
                    snap['slow'] = True
                else:
                    raise
            else:
                raise
        _settle(page)
        info = _collect(page)
        if is_challenge(info) and not is_filter_page(info, page.url):
            log('   چالش ضدربات دیده شد؛ صبر برای عبور خودکار ...')
            end = time.time() + CHALLENGE_WAIT_S
            while time.time() < end:
                page.wait_for_timeout(2500)
                _settle(page, 4000)
                info = _collect(page)
                if not is_challenge(info):
                    break
        snap.update(info)
        snap['loaded'] = True
        snap['final_url'] = page.url
        r = nav['resp']
        if r is not None:
            snap['status'] = r.status
            try:
                snap['content_type'] = r.headers.get('content-type', '') or ''
            except Exception:
                pass
            try:
                # بدنه‌ی همان پاسخ نهایی صفحه (برای بررسی بایت‌های نامعتبر UTF-8).
                # شرط میزبان برداشته شد تا اگر ریدایرکت داخلی بوده هم سورس خام داشته باشیم
                # و بیش از حد «بررسی نشد» نگیریم.
                if 200 <= r.status < 300:
                    snap['raw'] = r.body()
            except Exception:
                pass
    except Exception as e:
        msg = str(e)
        kind, code = classify_error(msg)
        snap['error_kind'] = kind
        snap['error_code'] = code
        snap['error_msg'] = short(msg.split('\n')[0], 160)
    finally:
        snap['load_s'] = time.time() - t0
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
    return snap


def _foreign_declared_host(snap):
    """اگر canonical یا og:url صفحه به دامنه‌ی غیرهم‌برند اشاره کند، همان هاست برگردانده می‌شود.
    این حالت یعنی احتمال دارد صفحه‌ی سایت دیگری به ما نشان داده شده باشد (VPN/کلوکینگ)."""
    req = host_of(snap['url'])
    if not req:
        return ''
    fin = host_of(snap.get('final_url') or snap['url'])
    if fin and reg_domain(fin) != reg_domain(req):
        return ''   # ریدایرکت به دامنه‌ی دیگر جداگانه گزارش می‌شود
    for u in list(snap.get('canon') or []) + list(snap.get('ogurl') or []):
        h = host_of(u)
        if not h or h == fin:
            continue
        if reg_domain(h) == reg_domain(req) or same_brand(req, h):
            continue
        return h
    return ''


def _detect(snap):
    """تشخیص صفحه‌های جایگزین/مشکل‌دار روی صفحه‌ای که لود شده."""
    if not snap.get('loaded'):
        return
    fin = snap.get('final_url') or snap['url']
    title = norm_fa(snap.get('title', ''))
    text_raw = clean_text(snap.get('text', ''))
    text = norm_fa(text_raw[:6000])
    both = title + ' ' + text
    html = (snap.get('html') or '')[:300000].lower()
    # سایت‌های واقعی متن زیادی دارند؛ صفحه‌های «برو به آدرس جدید / IP مجاز نیست» کوتاه‌اند.
    # متن‌هایی مثل «آدرس جدید بدون فیلتر» روی سایت اصلی زیاد است، پس فقط در صفحه کوتاه حساب می‌شوند.
    small = len(text_raw) < 400
    medium = len(text_raw) < 800

    snap['filter'] = is_filter_page(snap, fin)
    snap['challenge'] = (not snap['filter']) and is_challenge(snap)

    w = _any(BLOCK_TITLES, title)
    if w:
        snap['block_msg'] = f'صفحه محدودیت/مسدودی نمایش داده شد («{w}»)'
    elif medium and _any(GEO_WORDS, both):
        snap['block_msg'] = f'صفحه محدودیت IP/VPN یا کشور نمایش داده شد («{_any(GEO_WORDS, both)}»)'
    else:
        refresh = snap.get('refresh') or ''
        m = re.search(r'url\s*=\s*[\'"]?([^\'" >]+)', refresh, re.I)
        if m:
            target = m.group(1)
            th = host_of(target if '://' in target else 'https://x/' + target) if '://' in target else ''
            if th and reg_domain(th) != reg_domain(host_of(fin)):
                snap['block_msg'] = f'صفحه انتقال (meta refresh) به دامنه دیگر: {th}'
        if not snap.get('block_msg') and medium and _any(REDIRECT_WORDS, both):
            snap['block_msg'] = f'صفحه «رفتن به آدرس جدید/دیگر» نمایش داده شد («{_any(REDIRECT_WORDS, both)}»)'

    # صفحه‌ی متعلق به دامنه‌ی دیگر (canonical/og:url) → یعنی صفحه‌ی سایت اشتباه برگشته.
    # به‌صورت «بررسی نشد» ثبت می‌شود (نه «بررسی دستی») تا کاربر مجبور به چک دستی نشود
    # و در دور دوم، خودِ اسکریپت همان سایت را دوباره بررسی می‌کند.
    if not snap.get('block_msg'):
        snap['foreign'] = _foreign_declared_host(snap)

    if title.startswith('index of /'):
        snap['page_error'] = 'لیست فایل‌های سرور (Index of) به‌جای سایت'
    elif _any(PARKED_WORDS, title) or (medium and _any(PARKED_WORDS, text)):
        snap['page_error'] = f'صفحه پارک/پیش‌فرض هاست یا در دست ساخت («{_any(PARKED_WORDS, both)}»)'
    elif _any(SERVER_ERR_WORDS, both):
        snap['page_error'] = f'خطای سرور/دیتابیس روی صفحه («{_any(SERVER_ERR_WORDS, both)}»)'
    elif PHP_ERR_RE.search(text_raw[:20000]):
        snap['page_error'] = 'خطای PHP روی صفحه نمایش داده می‌شود'
    elif SOFT404_RE.search(title) and small and (snap.get('status') or 200) < 400:
        snap['page_error'] = 'صفحه اصلی «پیدا نشد/404» نشان می‌دهد (Soft 404)'
    elif not text_raw and (snap.get('elements') or 0) < 5:
        snap['page_error'] = 'صفحه سفید (بدنه خالی)'


def page_verdict(snap):
    fin = snap.get('final_url') or snap['url']
    info = []
    if snap.get('status'):
        info.append(f"HTTP {snap['status']}")
    if snap.get('load_s') is not None:
        info.append(f"{snap['load_s']:.1f}s")
    if (snap.get('attempts') or 1) > 1:
        info.append(f"تلاش {snap['attempts']}")
    if snap.get('slow'):
        info.append('لود بسیار کند (بیش از ۴۵ ثانیه)')
    info = ' | '.join(info)

    def V(level, status, detail='', content_ok=False):
        d = ' | '.join(x for x in (detail, info) if x)
        return {'level': level, 'status': status, 'details': d or '-', 'content_ok': content_ok}

    ek = snap.get('error_kind')
    if ek:
        d = ' '.join(x for x in (snap.get('error_code'), '' if snap.get('error_code') else snap.get('error_msg')) if x)
        if ek == 'offline':
            return V('skip', 'بررسی نشد: اینترنت/VPN قطع بود', d)
        if ek == 'vpn':
            return V('skip', 'بررسی نشد: صفحه فیلترینگ برگشت (VPN/DNS درست وصل نبود)', d)
        if ek == 'dns':
            return V('err', 'خطا: DNS — دامنه resolve نمی‌شود (منقضی/بدون رکورد)', d)
        if ek == 'refused':
            return V('err', 'خطا: اتصال رد شد (سرور/پورت بسته است)', d)
        if ek == 'cert':
            return V('err', 'خطا: گواهی SSL نامعتبر است', d)
        if ek == 'redirect_loop':
            return V('err', 'خطا: ریدایرکت بی‌پایان (Too many redirects)', d)
        if ek == 'conn_timeout':
            return V('err', 'خطا: سرور پاسخ نمی‌دهد (Connection timed out)', d)
        if ek in ('ssl_proto', 'network'):
            return V('warn', 'نیاز به بررسی دستی: اتصال قطع شد — احتمال VPN/فیلترینگ', d)
        if ek == 'timeout':
            return V('warn', 'نیاز به بررسی دستی: صفحه در زمان مجاز لود نشد', d)
        return V('warn', 'نیاز به بررسی دستی: خطای ناشناخته شبکه', d)

    raw_status = snap.get('status')
    # اگر صفحه‌ای باز شده اما پاسخ navigation در دسترس نبوده، سالم اعلام نکن.
    # این حالت در timeoutهای جزئی/پاسخ‌های غیرمعمول ممکن است رخ دهد.
    if raw_status is None:
        if snap.get('loaded') and (snap.get('title') or snap.get('text')):
            return V('warn', 'نیاز به بررسی دستی: کد پاسخ HTTP دریافت نشد', fin)
        return V('warn', 'نیاز به بررسی دستی: نتیجه لود صفحه ناقص است', fin)
    st = raw_status
    if snap.get('filter'):
        return V('skip', 'بررسی نشد: صفحه فیلترینگ برگشت (VPN/DNS درست وصل نبود)', fin)
    if snap.get('challenge'):
        return V('warn', 'نیاز به بررسی دستی: چالش ضدربات (Cloudflare/Arvan) رد نشد — در مرورگر ببینید', fin)
    if st in (403, 451):
        return V('warn', f'نیاز به بررسی دستی: دسترسی رد شد ({st}) — احتمالا محدودیت IP/VPN', fin)
    if st == 429:
        return V('warn', 'نیاز به بررسی دستی: محدودیت تعداد درخواست (429)', fin)
    if st in (404, 410):
        return V('err', f'خطا: صفحه اصلی پیدا نشد ({st})', fin)
    if 520 <= st <= 527:
        return V('err', f'خطا: کلودفلر — {CF_CODES.get(st, "خطای سرور اصلی")} ({st})', fin)
    if st >= 500:
        return V('err', f'خطا: خطای سرور ({st})', fin)
    if st >= 400:
        return V('err', f'خطا: خطای HTTP ({st})', fin)
    if snap.get('foreign'):
        return V('skip', f'بررسی نشد: صفحه‌ی سایت دیگری برگشت (canonical/og:url → {snap["foreign"]}) '
                         '— با VPN/آی‌پی دیگر دوباره اجرا شود', fin)
    if snap.get('block_msg'):
        return V('warn', 'نیاز به بررسی دستی: ' + snap['block_msg'], fin)
    if snap.get('page_error'):
        return V('err', 'خطا: ' + snap['page_error'], fin)

    oh, fh = host_of(snap['url']), host_of(fin)
    if fh and reg_domain(fh) != reg_domain(oh):
        if REDIRECT_SAME_BRAND_OK and same_brand(oh, fh):
            return V('ok', f'سالم (ریدایرکت به {fh})', fin, True)
        return V('warn', f'نیاز به بررسی دستی: ریدایرکت به دامنه دیگر ({fh})', fin)
    if fin.lower().startswith('http://'):
        return V('warn', 'نیاز به بررسی دستی: سایت به http بدون SSL منتقل شد', fin)
    return V('ok', 'سالم', '', True)


def take_snapshot(ctx, url):
    """یک بار سایت را کامل لود می‌کند؛ همه چک‌ها روی همین نتیجه کار می‌کنند."""
    url = normalize_url(url)
    attempt, net_waits, snap = 0, 0, None
    while attempt < MAX_ATTEMPTS:
        attempt += 1
        snap = _load_once(ctx, url)
        snap['attempts'] = attempt
        ek = snap.get('error_kind')
        if not ek:
            if is_filter_page(snap, snap.get('final_url')):
                # صفحه فیلترینگ = مشکل اتصال ما، نه سایت
                if attempt < MAX_ATTEMPTS:
                    log('   صفحه فیلترینگ برگشت؛ صبر و تلاش دوباره ...')
                    time.sleep(15)
                    continue
                break
            if (snap.get('status') in RETRY_STATUSES and attempt < MAX_ATTEMPTS
                    and not is_challenge(snap)):
                log(f"   HTTP {snap.get('status')}؛ تلاش دوباره ...")
                time.sleep(4 * attempt)
                continue
            break
        if not internet_ok(ctx):
            if net_waits >= 2 or not wait_for_internet(ctx, 150):
                snap['error_kind'] = 'offline'
                break
            net_waits += 1
            attempt -= 1
            continue
        if ek in ('dns', 'refused', 'cert', 'redirect_loop') and attempt >= 2:
            break
        if attempt < MAX_ATTEMPTS:
            time.sleep(3 * attempt)
    _detect(snap)
    snap['verdict'] = page_verdict(snap)
    return snap


def content_gate(snap):
    """برای چک‌های محتوایی: اگر صفحه واقعی سایت نیست، متن «بررسی نشد» برمی‌گرداند."""
    v = snap.get('verdict')
    if not v:
        return 'بررسی نشد: نتیجه لود صفحه آماده نیست'
    if v['content_ok']:
        return None
    if v['level'] == 'skip':
        return v['status']
    reason = v['status'].split(':', 1)[-1].strip()
    return f'بررسی نشد: صفحه اصلی سالم نبود ({short(reason, 70)})'


def redirect_note(snap):
    fin = snap.get('final_url') or ''
    fh = host_of(fin)
    if fh and reg_domain(fh) != reg_domain(host_of(snap['url'])):
        return f'  [از {fh}]'
    return ''

# ----------------------------------------------------------------- بررسی فایل تصویر
def _is_image_bytes(b, content_type=''):
    """امضای چند فرمت رایج تصویر را بررسی می‌کند؛ MIME به‌تنهایی کافی نیست."""
    if not b:
        return False
    h = b[:64]
    if h.startswith(b'\x89PNG\r\n\x1a\n') or h.startswith(b'\xff\xd8\xff') or h.startswith(b'GIF8'):
        return True
    if h.startswith(b'RIFF') and b[8:12] == b'WEBP':
        return True
    if h.startswith(b'\x00\x00\x01\x00') or h.startswith(b'\x00\x00\x02\x00') or h.startswith(b'BM'):
        return True
    # ICO و فرمت‌های HEIF/AVIF از خانواده ISO-BMFF هستند؛ MP4 را قبول نکن.
    if b[4:8] == b'ftyp':
        brand = b[8:16].lower()
        if brand[:4] in (b'avif', b'avis', b'heic', b'heix', b'hevc', b'hevx', b'mif1'):
            return True
    head = b[:3000].lstrip().lower()
    if b'<svg' in head and (content_type.startswith('image/svg') or b'xmlns="http://www.w3.org/2000/svg"' in head):
        return True
    return False

def check_asset(ctx, url, referer):
    """دانلود فایل تصویر. دور زدن مسدودی با باز کردن تب واقعی."""
    if not url: return 'err', 'آدرس خالی'
    if url.startswith('data:'):
        return ('ok', 'data URI') if url.lower().startswith('data:image/') else ('err', 'data URI غیرتصویری')
    if not url.lower().startswith(('http://', 'https://')): return 'err', 'آدرس نامعتبر'

    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    
    # 1. تلاش اول: درخواست سریع با request.get
    for attempt in (1, 2):
        r = None
        try:
            headers = {'User-Agent': ua, 'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8', 'Accept-Language': 'fa,en;q=0.9'}
            if attempt == 1: headers['Referer'] = referer
            r = ctx.request.get(url, timeout=15000, max_redirects=10, headers=headers)
            st = r.status
            if st in (429, 500, 502, 503, 504) and attempt == 1:
                time.sleep(2)
                continue
            if st in (404, 410): return 'err', f'فایل وجود ندارد ({st})'
            if st >= 400 and st not in (401, 403, 451): return 'err', f'خطای دریافت فایل ({st})'
            
            # اگر عکس واقعا دانلود شد (و خطای مسدودی نداشتیم)
            if st not in (401, 403, 451):
                body = r.body() or b''
                ctype = (r.headers.get('content-type', '') or '').split(';')[0].strip().lower()
                if _is_image_bytes(body, ctype):
                    kb = max(1, len(body) // 1024)
                    return 'ok', f'{ctype or "image"} — {kb}KB'
        except Exception:
            pass
        finally:
            if r:
                try: r.dispose()
                except: pass

    # 2. تلاش دوم (ضد بلاک): باز کردن مستقیم لینک در یک تب واقعی مرورگر
    page = None
    try:
        page = ctx.new_page()
        page.set_extra_http_headers({'Referer': referer})
        r = page.goto(url, timeout=20000)
        if r:
            st = r.status
            if st >= 400: return 'err', f'خطای دریافت فایل ({st})'
            
            body = r.body() or b''
            if len(body) == 0: return 'err', 'فایل خالی است (0 بایت)'
            
            ctype = (r.headers.get('content-type', '') or '').split(';')[0].strip().lower()
            head = body[:500].lstrip().lower()
            
            if (head.startswith(b'<!doctype html') or head.startswith(b'<html') or b'<html' in head[:200]) and not _is_image_bytes(body, ctype):
                return 'err', 'به‌جای تصویر یک صفحه HTML برگشت'
            
            if _is_image_bytes(body, ctype):
                kb = max(1, len(body) // 1024)
                return 'ok', f'{ctype or "image"} — {kb}KB'
            else:
                return 'err', f'فایل تصویر معتبر نیست ({ctype or "نامشخص"})'
                
        return 'warn', 'دانلود فایل ممکن نشد (ارتباط قطع شد)'
    except Exception as e:
        kind, code = classify_error(str(e))
        if kind in ('dns', 'refused', 'cert'):
            return 'err', f'سرور فایل در دسترس نیست ({code or kind})'
        return 'warn', f'دانلود فایل ممکن نشد ({code or kind})'
    finally:
        if page:
            try: page.close()
            except: pass

# ----------------------------------------------------------------- CSV و پیشرفت
def csv_path(module):
    return os.path.join(REPORTS_DIR, module.CSV_NAME)


def init_csv(module):
    with open(csv_path(module), 'w', newline='', encoding='utf-8-sig') as f:
        csv.DictWriter(f, fieldnames=module.FIELDS).writeheader()


def append_row(module, row):
    with open(csv_path(module), 'a', newline='', encoding='utf-8-sig') as f:
        csv.DictWriter(f, fieldnames=module.FIELDS, extrasaction='ignore', restval='').writerow(row)


def upsert_row(module, row):
    path = csv_path(module)
    rows, replaced = [], False
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                for r in csv.DictReader(f):
                    r = {k: v for k, v in r.items() if k is not None}
                    if normalize_url(r.get('URL', '')) == row['URL']:
                        if not replaced:
                            rows.append(row)
                            replaced = True
                    else:
                        rows.append(r)
        except Exception:
            rows = []
    if not replaced:
        rows.append(row)
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=module.FIELDS, extrasaction='ignore', restval='')
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)


def run_analyze(module, ctx, snap):
    row = {f: '' for f in module.FIELDS}
    try:
        row.update(module.analyze(ctx, snap) or {})
    except Exception as e:
        traceback.print_exc()
        row['Status'] = f'بررسی نشد: خطای داخلی اسکریپت ({type(e).__name__})'
    row = {k: safe_csv(v) for k, v in row.items()}
    row['URL'] = snap['url']
    return row


def status_level(s):
    s = (s or '').strip().lstrip("'")
    if not s or s in ('-', 'بررسی نشده'):
        return 'idle'
    if s.startswith('سالم') or 'بدون کاراکتر' in s:
        return 'ok'
    if s.startswith('خطا'):
        return 'err'
    if s.startswith('نیاز'):
        return 'warn'
    if s.startswith('بررسی نشد'):
        return 'skip'
    if 'خطا' in s:
        return 'err'
    if 'نیاز' in s:
        return 'warn'
    return 'idle'


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def write_progress(data):
    data['updated_at'] = _now()
    data['updated_ts'] = time.time()
    tmp = PROGRESS_FILE + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, PROGRESS_FILE)
    except Exception:
        pass


def read_progress():
    try:
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def stop_requested():
    return os.path.exists(STOP_FILE)


def human_pause():
    time.sleep(random.uniform(*PAUSE_RANGE))


def _is_network_suspect(snap):
    v = snap['verdict']
    if v['level'] == 'skip':
        return True
    return snap.get('error_kind') in ('ssl_proto', 'network', 'timeout', 'other')

# ----------------------------------------------------------------- اجرای کامل
def run_checks(modules, urls=None):
    """اجرای یک یا چند چک روی همه لینک‌ها؛ هر سایت فقط یک بار باز می‌شود."""
    from playwright.sync_api import sync_playwright
    setup_console()
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)
    urls = urls if urls is not None else load_urls()
    tools = [m.TOOL_ID for m in modules]
    prog = {'state': 'running', 'tools': tools, 'total': len(urls), 'done': 0,
            'current_url': '', 'phase': 'شروع', 'started_at': _now(), 'finished_at': '',
            'message': '', 'counts': {'ok': 0, 'err': 0, 'warn': 0, 'skip': 0}}
    write_progress(prog)

    def finish(state, message):
        prog.update({'state': state, 'message': message, 'finished_at': _now(), 'current_url': ''})
        write_progress(prog)
        log(message)

    if not urls:
        finish('error', 'فایل urls.txt خالی است یا پیدا نشد.')
        return 1

    with sync_playwright() as p:
        browser, ctx = open_browser(p)
        try:
            prog['phase'] = 'بررسی اتصال اینترنت/VPN'
            write_progress(prog)
            if not wait_for_internet(ctx, 30):
                finish('error', 'اتصال اینترنت/VPN برقرار نیست؛ اسکن شروع نشد و گزارش‌های قبلی دست نخوردند.')
                return 2
            for m in modules:
                init_csv(m)

            suspects, filter_streak, cert_streak, cert_max = [], 0, 0, 0
            prog['phase'] = 'اسکن'
            for i, url in enumerate(urls):
                if stop_requested():
                    finish('stopped', f'اسکن توسط کاربر متوقف شد ({i}/{len(urls)}).')
                    return 4
                prog.update({'done': i, 'current_url': url})
                write_progress(prog)
                log(f'[{i + 1}/{len(urls)}] {url}')
                snap = take_snapshot(ctx, url)
                v = snap['verdict']
                log(f"   → {v['status']}")
                if snap.get('error_kind') == 'cert':
                    cert_streak += 1
                    cert_max = max(cert_max, cert_streak)
                else:
                    cert_streak = 0

                if snap.get('error_kind') == 'offline':
                    for m in modules:
                        for u in urls[i:]:
                            append_row(m, {'URL': u, 'Status': 'بررسی نشد: اینترنت/VPN قطع بود'})
                    finish('error', f'اینترنت/VPN قطع شد و وصل نشد؛ اسکن در {i}/{len(urls)} متوقف شد. بعد از وصل شدن دوباره اجرا کنید.')
                    return 3

                filter_streak = filter_streak + 1 if snap.get('filter') else 0
                if filter_streak >= 4:
                    for m in modules:
                        for u in urls[i + 1:]:
                            append_row(m, {'URL': u, 'Status': 'بررسی نشد: VPN وصل نبود'})
                    for m in modules:
                        append_row(m, run_analyze(m, ctx, snap))
                    finish('error', 'چند سایت پشت‌سرهم صفحه فیلترینگ دادند: VPN وصل نیست یا DNS نشت دارد. VPN را درست کنید و دوباره اجرا کنید.')
                    return 5

                for m in modules:
                    append_row(m, run_analyze(m, ctx, snap))
                prog['counts'][v['level']] = prog['counts'].get(v['level'], 0) + 1
                if _is_network_suspect(snap):
                    suspects.append(url)
                human_pause()

            # دور دوم: سایت‌هایی که به خاطر شبکه/VPN مشکوک بودند یک بار دیگر بررسی می‌شوند
            if suspects and not stop_requested():
                prog.update({'phase': f'بررسی مجدد {len(suspects)} سایت مشکوک به مشکل شبکه', 'done': len(urls)})
                write_progress(prog)
                log(f'دور دوم برای {len(suspects)} سایت ...')
                time.sleep(10)
                wait_for_internet(ctx, 60)
                for url in suspects:
                    if stop_requested():
                        break
                    prog['current_url'] = url
                    write_progress(prog)
                    snap = take_snapshot(ctx, url)
                    if snap.get('error_kind') == 'offline':
                        break
                    log(f"   [دور دوم] {url} → {snap['verdict']['status']}")
                    for m in modules:
                        upsert_row(m, run_analyze(m, ctx, snap))
                    human_pause()

            prog['done'] = len(urls)
            notes = []
            if cert_max >= 3:
                notes.append('چند سایت پشت‌سرهم خطای گواهی SSL داشتند؛ اگر VPN یا آنتی‌ویروس شما '
                             'TLS را باز می‌کند، ستون سلامت را دستی تأیید کنید.')
            skipped = prog['counts'].get('skip', 0)
            if skipped >= max(3, len(urls) // 10):
                notes.append(f'{skipped} سایت «بررسی نشد» شدند؛ احتمالا VPN در آن بازه ناپایدار '
                             'بوده و باید دوباره بررسی شوند.')
            finish('done', f'اسکن تمام شد: {len(urls)} سایت.' + (('  |  ' + '  |  '.join(notes)) if notes else ''))
            return 0
        except Exception as e:
            traceback.print_exc()
            finish('error', f'خطای داخلی اسکریپت: {type(e).__name__}: {short(str(e), 150)}')
            return 9
        finally:
            try:
                ctx.close()
                browser.close()
            except Exception:
                pass


def load_modules(tool_ids=None):
    import importlib
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    ids = tool_ids or ALL_TOOLS
    return [importlib.import_module(f'check_{t}') for t in ids]
