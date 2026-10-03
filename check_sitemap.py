# -*- coding: utf-8 -*-
"""
check_sitemap.py - بررسی وجود و اعتبار سایت‌مپ
اجرای تنها:  python check_sitemap.py
خروجی:       reports/sitemap_report.csv

منطق چهار مرحله‌ای (short-circuit — به محض برخورد به اولین ایراد، پایان):

  ۱) اگر خود صفحه اصلی سالم نیست → «بررسی نشد: ...» (مثل بقیه چک‌ها)
  ۲) robots.txt سایت باز می‌شود؟
       - اگر 404/410 یا کلاً باز نشد → «خطا: فایل robots.txt وجود ندارد یا باز نمی‌شود»
       - اگر 403/429 یا خطای شبکه موقت → «نیاز به بررسی دستی: ...»
  ۳) در robots.txt خط Sitemap تعریف شده؟ (case-insensitive، چند خطی هم ممکنه)
       - اگر نبود → «خطا: در robots.txt خط Sitemap تعریف نشده»
  ۴) هر لینک Sitemap در robots باز می‌شود و محتوایش معتبر است؟
       - اگر لینک 4xx/5xx داد → «خطا: لینک sitemap باز نمی‌شود (کد ...)»
       - اگر محتوا XML معتبر نیست (نه <urlset و نه <sitemapindex و نه <?xml) → «خطا: محتوای sitemap معتبر XML نیست»
       - در غیر این صورت → «سالم (N لینک sitemap در robots.txt)»

نکته: این چک «محتوای لینک‌های داخل sitemap» را بررسی نمی‌کند. فقط وجود، باز شدن و فرمت XML.
نکته‌ی مهم تطبیق با پروژه:
  - از همان `ctx.request` خود Playwright context استفاده می‌شود (UA/locale/cookie
    هم‌مانند بقیه چک‌ها) تا سایت‌هایی که ضدربات دارند کمتر الکی بلاک کنند.
  - زمان‌بندی سخت است (12 ثانیه برای robots و 15 ثانیه برای هر sitemap) تا یک
    سایت کند کل اسکن ۹۳-سایتی را معطل نکند.
  - اگر `content_gate` بگوید صفحه اصلی مشکل داشته، این چک حتی robots را هم
    نمی‌خواند و «بررسی نشد» ثبت می‌کند — دقیقا مثل بقیه چک‌ها.
"""
import re
import sys
from urllib.parse import urlsplit, urljoin
import qa_core as qc

TOOL_ID = 'sitemap'
CSV_NAME = 'sitemap_report.csv'
FIELDS = ['URL', 'Sitemap URL', 'Status']

# حداکثر زمان‌ها (ثانیه → ms برای playwright request)
ROBOTS_TIMEOUT_MS = 12000
SITEMAP_TIMEOUT_MS = 15000
# حداکثر تعداد لینک sitemap که از robots می‌خوانیم (بعضی سایت‌ها ده‌ها sitemap-index دارند)
MAX_SITEMAPS = 5
# حداکثر حجم بدنه که برای تشخیص XML می‌خوانیم (برای sitemap‌های خیلی بزرگ)
MAX_PEEK_BYTES = 65536


def _parse_sitemaps(robots_text):
    """خطوط `Sitemap: ...` را از robots.txt استخراج می‌کند (case-insensitive، چندخطی)."""
    out = []
    for line in (robots_text or '').splitlines():
        m = re.match(r'^\s*sitemap\s*:\s*(\S+.*?)\s*$', line, re.I)
        if m:
            out.append(m.group(1).strip())
    # یکتا کردن با حفظ ترتیب
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _looks_like_xml(body_bytes, content_type=''):
    """آیا بدنه، یک sitemap XML معتبر به‌نظر می‌رسد؟
    پذیرفته می‌شود: شروع با <?xml، یا داشتن <urlset یا <sitemapindex در هد.
    نشانه‌های HTML (<!doctype html / <html) رد می‌کند.
    """
    if not body_bytes:
        return False
    head = body_bytes[:MAX_PEEK_BYTES].lstrip()
    low = head[:4096].lower()
    # اگر HTML برگشت، سایت‌مپ سالم نیست (معمولا صفحه خطا / لاگین)
    if low.startswith(b'<!doctype html') or low.startswith(b'<html') or b'<html' in low[:200]:
        return False
    # XML معمولی یا gzipped (در robots معمولا به .xml.gz هم اشاره می‌شود)
    if head.startswith(b'\x1f\x8b'):  # gzip magic
        return True
    if head.startswith(b'<?xml'):
        return True
    if b'<urlset' in low or b'<sitemapindex' in low:
        return True
    # بعضی سرورها content-type را درست می‌دهند ولی بدنه با whitespace/BOM شروع می‌شود
    ct = (content_type or '').lower()
    if ('xml' in ct) and (b'<' in low[:200]):
        return True
    return False


def _fetch(ctx, url, timeout_ms):
    """درخواست سبک با همان context؛ خروجی: (status, body, content_type, err_kind)
    err_kind: '' موفق، 'network' خطای شبکه/تایم‌اوت، 'bad_url' فرمت اشتباه"""
    if not url or not url.lower().startswith(('http://', 'https://')):
        return None, b'', '', 'bad_url'
    r = None
    try:
        r = ctx.request.get(
            url,
            timeout=timeout_ms,
            max_redirects=5,
            headers={
                'Accept': 'text/plain, application/xml, text/xml, */*;q=0.5',
                'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
            },
        )
        status = r.status
        try:
            body = r.body() or b''
        except Exception:
            body = b''
        try:
            ctype = (r.headers.get('content-type', '') or '').split(';')[0].strip().lower()
        except Exception:
            ctype = ''
        return status, body, ctype, ''
    except Exception:
        return None, b'', '', 'network'
    finally:
        if r is not None:
            try:
                r.dispose()
            except Exception:
                pass


def analyze(ctx, snap):
    # مرحله ۱: اگر خود صفحه اصلی سالم نیست، چیزی چک نمی‌کنیم
    gate = qc.content_gate(snap)
    if gate:
        return {'Sitemap URL': '-', 'Status': gate}

    # ساخت origin از آدرس نهایی (در صورت ریدایرکت، robots را از دامنه مقصد می‌خوانیم)
    base = snap.get('final_url') or snap.get('url') or ''
    p = urlsplit(base)
    if not p.scheme or not p.netloc:
        return {'Sitemap URL': '-', 'Status': 'بررسی نشد: آدرس سایت نامعتبر است'}
    robots_url = f'{p.scheme}://{p.netloc}/robots.txt'

    # مرحله ۲: robots.txt
    status, body, ctype, err = _fetch(ctx, robots_url, ROBOTS_TIMEOUT_MS)
    if err == 'network' or status is None:
        return {'Sitemap URL': robots_url,
                'Status': 'نیاز به بررسی دستی: robots.txt باز نشد (خطای شبکه/تایم‌اوت)'}
    if status in (404, 410):
        return {'Sitemap URL': robots_url,
                'Status': 'خطا: فایل robots.txt وجود ندارد'}
    if status in (401, 403, 429, 451):
        return {'Sitemap URL': robots_url,
                'Status': f'نیاز به بررسی دستی: دسترسی به robots.txt محدود است ({status})'}
    if status >= 500:
        return {'Sitemap URL': robots_url,
                'Status': f'نیاز به بررسی دستی: خطای سرور در دریافت robots.txt ({status})'}
    if status >= 400:
        return {'Sitemap URL': robots_url,
                'Status': f'خطا: robots.txt باز نمی‌شود ({status})'}
    # کد موفق ولی بدنه خالی/HTML هم یعنی robots درست سرو نشده
    try:
        text = body.decode('utf-8', errors='replace')
    except Exception:
        text = ''
    low_head = (body[:400] or b'').lstrip().lower()
    if (low_head.startswith(b'<!doctype html') or low_head.startswith(b'<html')
            or b'<html' in low_head[:200]):
        return {'Sitemap URL': robots_url,
                'Status': 'خطا: به‌جای robots.txt یک صفحه HTML برگشت'}
    if not text.strip():
        return {'Sitemap URL': robots_url,
                'Status': 'خطا: فایل robots.txt خالی است'}

    # مرحله ۳: استخراج خط‌های Sitemap
    sitemaps = _parse_sitemaps(text)
    if not sitemaps:
        return {'Sitemap URL': '-',
                'Status': 'خطا: در robots.txt خط Sitemap تعریف نشده'}

    # مرحله ۴: هر لینک Sitemap را امتحان می‌کنیم. به محض یافتن یک sitemap سالم → سالم.
    # لینک‌های نسبی هم (گرچه کمیاب) نسبت به origin حل می‌شوند.
    tried = []
    for raw in sitemaps[:MAX_SITEMAPS]:
        s_url = raw if raw.lower().startswith(('http://', 'https://')) else urljoin(robots_url, raw)
        st, sbody, sctype, serr = _fetch(ctx, s_url, SITEMAP_TIMEOUT_MS)
        tried.append((s_url, st, sctype, serr, sbody))
        if serr == 'bad_url':
            continue
        if serr == 'network' or st is None:
            continue
        if st in (401, 403, 429, 451):
            continue
        if st >= 400:
            continue
        if _looks_like_xml(sbody, sctype):
            total = len(sitemaps)
            if total == 1:
                extra = ''
            else:
                extra = f' (از {total} لینک sitemap در robots)'
            # اگر لینک اول خراب بود ولی لینک بعدی سالم بود، همین کافی است و «سالم» می‌شود.
            return {'Sitemap URL': s_url, 'Status': f'سالم{extra}'}

    # هیچ sitemapی سالم نبود → تشخیص دقیق‌ترین دلیل برای اولین لینک
    first_url, first_st, first_ct, first_err, first_body = tried[0]
    if first_err == 'network' or first_st is None:
        return {'Sitemap URL': first_url,
                'Status': 'نیاز به بررسی دستی: لینک sitemap باز نشد (خطای شبکه/تایم‌اوت)'}
    if first_st in (404, 410):
        return {'Sitemap URL': first_url,
                'Status': f'خطا: لینک sitemap در robots وجود ندارد ({first_st})'}
    if first_st in (401, 403, 429, 451):
        return {'Sitemap URL': first_url,
                'Status': f'نیاز به بررسی دستی: دسترسی به sitemap محدود است ({first_st})'}
    if first_st >= 400:
        return {'Sitemap URL': first_url,
                'Status': f'خطا: لینک sitemap باز نمی‌شود ({first_st})'}
    # کد 2xx ولی محتوا XML معتبر نیست
    low = (first_body[:400] or b'').lstrip().lower()
    if (low.startswith(b'<!doctype html') or low.startswith(b'<html')
            or b'<html' in low[:200]):
        return {'Sitemap URL': first_url,
                'Status': 'خطا: به‌جای sitemap یک صفحه HTML برگشت'}
    return {'Sitemap URL': first_url,
            'Status': 'خطا: محتوای sitemap معتبر XML نیست'}


if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
