# -*- coding: utf-8 -*-
"""
retry_single.py - اسکن سریع یک سایت (دکمه «اسکن سریع» در پنل)
اجرا:  python retry_single.py delbet.site

دقیقا همان منطق اسکن کامل را اجرا می‌کند و ردیف همان سایت را در هر ۶ گزارش جایگزین می‌کند
(نه اضافه؛ ردیف تکراری ساخته نمی‌شود).
"""
import sys
import qa_core as qc


def main():
    qc.setup_console()
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        qc.log('آدرس سایت داده نشده است.')
        return 1
    url = qc.normalize_url(sys.argv[1])
    modules = qc.load_modules()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, ctx = qc.open_browser(p)
        try:
            if not qc.internet_ok(ctx):
                qc.log('اینترنت/VPN وصل نیست؛ گزارش تغییری نکرد.')
                return 2
            qc.log(f'اسکن سریع: {url}')
            snap = qc.take_snapshot(ctx, url)
            if snap.get('error_kind') == 'offline':
                qc.log('اینترنت/VPN در حین اسکن قطع شد؛ گزارش تغییری نکرد.')
                return 2
            for m in modules:
                row = qc.run_analyze(m, ctx, snap)
                qc.upsert_row(m, row)
                qc.log(f'  {m.TOOL_ID}: {row.get("Status")}')
            return 0
        finally:
            try:
                ctx.close()
                browser.close()
            except Exception:
                pass


if __name__ == '__main__':
    sys.exit(main())
