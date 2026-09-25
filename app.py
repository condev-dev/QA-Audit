# -*- coding: utf-8 -*-
"""
app.py - سرور پنل QA Master
اجرا:  python app.py   →  http://127.0.0.1:5000
(index.html باید داخل پوشه templates باشد)
"""
import os
import sys
import csv
import json
import time
import zipfile
import subprocess
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request

import qa_core as qc

BASE_DIR = qc.BASE_DIR
REPORTS_DIR = qc.REPORTS_DIR
URLS_FILE = qc.URLS_FILE
ARCHIVE_DIR = os.path.join(BASE_DIR, 'archives')
LOG_FILE = os.path.join(REPORTS_DIR, '_last_run.log')

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))

TOOLS = {
    'health': {'script': 'check_health.py', 'output': 'health_report.csv', 'name': 'سلامت سرور'},
    'title': {'script': 'check_title.py', 'output': 'title_report.csv', 'name': 'تایتل'},
    'description': {'script': 'check_description.py', 'output': 'description_report.csv', 'name': 'دیسکریپشن'},
    'og_image': {'script': 'check_og_image.py', 'output': 'og_image_report.csv', 'name': 'عکس OG'},
    'source_encoding': {'script': 'check_source_encoding.py', 'output': 'source_encoding_report.csv', 'name': 'سورس'},
    'favicon': {'script': 'check_favicon.py', 'output': 'favicon_report.csv', 'name': 'فوآیکون'},
}
TEXT_FIELD = {'health': 'Details', 'title': 'Title Text', 'description': 'Description Text',
              'og_image': 'Image URL', 'source_encoding': 'Details', 'favicon': 'Favicon URL'}

# ---------------------------------------------------------------- مدیریت اجرا (فقط یک اسکن همزمان)
_job_lock = threading.Lock()
_job = {'proc': None, 'tools': [], 'kind': ''}


def _child_env():
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['QA_PLAIN_LOG'] = '1'
    return env


def _running():
    p = _job['proc']
    if p == 'sync':
        return True
    return p is not None and hasattr(p, 'poll') and p.poll() is None


def _start(cmd, tools, kind):
    with _job_lock:
        if _running():
            return False
        logf = open(LOG_FILE, 'w', encoding='utf-8')
        _job['proc'] = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=logf, stderr=subprocess.STDOUT,
                                        env=_child_env())
        _job['tools'] = tools
        _job['kind'] = kind
        threading.Thread(target=lambda: (_job['proc'].wait(), logf.close()), daemon=True).start()
        return True


def _busy_response():
    return jsonify({'status': 'busy', 'message': 'یک اسکن دیگر در حال اجراست؛ صبر کنید تا تمام شود.'}), 409

# ---------------------------------------------------------------- خواندن گزارش‌ها
def get_tool_data(output_filename):
    data = {}
    path = os.path.join(REPORTS_DIR, output_filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    clean = {str(k): ('' if v is None else str(v)) for k, v in row.items() if k is not None}
                    key = qc.normalize_url(clean.get('URL', ''))
                    if key:
                        clean['URL'] = key
                        data[key] = clean
        except Exception as e:
            print(f'Error reading CSV {path}: {e}')
    return list(data.values()), data


def read_raw_urls():
    if not os.path.exists(URLS_FILE):
        return []
    with open(URLS_FILE, 'r', encoding='utf-8-sig') as f:
        return [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]

# ---------------------------------------------------------------- صفحات
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/urls/raw', methods=['GET'])
def get_raw_urls():
    return jsonify(read_raw_urls())


@app.route('/api/urls/save', methods=['POST'])
def save_raw_urls():
    urls = (request.get_json(silent=True) or {}).get('urls', [])
    seen, out = set(), []
    for u in urls:
        u = str(u).strip()
        k = qc.normalize_url(u)
        if u and k not in seen:
            seen.add(k)
            out.append(u)
    with open(URLS_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + ('\n' if out else ''))
    return jsonify({'status': 'success', 'count': len(out)})


@app.route('/urls')
def get_base_urls():
    reports = {t: get_tool_data(info['output'])[1] for t, info in TOOLS.items()}
    results, seen = [], set()
    for raw in read_raw_urls():
        key = qc.normalize_url(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        details, errors, warns, skips, checked = {}, [], [], [], 0
        for t, info in TOOLS.items():
            row = reports[t].get(key, {})
            st = row.get('Status', '') or 'بررسی نشده'
            lvl = qc.status_level(st) if row else 'idle'
            details[t] = {'status': st, 'level': lvl, 'text': row.get(TEXT_FIELD[t], '') or '-'}
            if t == 'health':
                details[t]['final_url'] = row.get('Final URL', '') or '-'
            if lvl != 'idle':
                checked += 1
            if lvl == 'err':
                errors.append(info['name'])
            elif lvl == 'warn':
                warns.append(info['name'])
            elif lvl == 'skip':
                skips.append(info['name'])
        if errors:
            overall = 'err'
        elif warns:
            overall = 'warn'
        elif skips:
            overall = 'skip'
        elif checked == len(TOOLS):
            overall = 'ok'
        else:
            overall = 'idle'
        results.append({'raw_url': raw, 'formatted_url': key, 'errors': errors, 'warnings': warns,
                        'skipped': skips, 'overall': overall, 'details': details})
    return jsonify(results)

# ---------------------------------------------------------------- اجرای چک‌ها
@app.route('/run/<tool_id>', methods=['POST'])
def run_tool(tool_id):
    if tool_id not in TOOLS:
        return jsonify({'status': 'error'}), 404
    ok = _start([sys.executable, os.path.join(BASE_DIR, TOOLS[tool_id]['script'])], [tool_id], 'tool')
    return jsonify({'status': 'started'}) if ok else _busy_response()


@app.route('/run_all', methods=['POST'])
def run_all():
    ok = _start([sys.executable, os.path.join(BASE_DIR, 'run_all.py')], list(TOOLS), 'all')
    return jsonify({'status': 'started'}) if ok else _busy_response()


@app.route('/stop', methods=['POST'])
def stop():
    if not _running():
        return jsonify({'status': 'idle'})
    open(qc.STOP_FILE, 'w').close()   # توقف تمیز بعد از سایت جاری (گزارش نصفه خراب نمی‌شود)
    return jsonify({'status': 'stopping'})


@app.route('/check_sitemap', methods=['POST'])
def check_sitemap():
    import re
    import urllib.request
    from urllib.parse import urlparse
    
    url = (request.get_json(silent=True) or {}).get('url')
    if not url:
        return jsonify({'status': 'error'})
    
    try:
        if not url.startswith('http'):
            url = 'https://' + url
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        def extract_sitemap(text):
            match = re.search(r'(?i)^sitemap\s*:\s*(https?://[^\s]+)', text or '', re.MULTILINE)
            return match.group(1).strip() if match else None

        # مرحله اول: تست سریع با حداکثر ۱.۵ ثانیه انتظار برای جلوگیری از معطلی فایروال
        try:
            req = urllib.request.Request(
                robots_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'}
            )
            with urllib.request.urlopen(req, timeout=1.5) as response:
                if response.status == 200:
                    s_url = extract_sitemap(response.read().decode('utf-8', errors='ignore'))
                    if s_url: return jsonify({'status': 'found', 'sitemap': s_url})
                    return jsonify({'status': 'not_found'})
        except Exception:
            pass
            
        # مرحله دوم: دور زدن فایروال با سرعت بالا (بدون انتظار برای رندر)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(
                    ignore_https_errors=True,
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'
                )
                page = ctx.new_page()
                
                # wait_until='commit' باعث می‌شود به محض دریافت متن، کار تمام شود
                r = page.goto(robots_url, timeout=10000, wait_until='commit')
                
                if r and r.status < 400:
                    s_url = extract_sitemap(r.body().decode('utf-8', errors='ignore'))
                    if s_url: return jsonify({'status': 'found', 'sitemap': s_url})
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
                    
        return jsonify({'status': 'not_found'})
    except Exception:
        return jsonify({'status': 'not_found'})

@app.route('/progress')
def progress():
    prog = qc.read_progress()
    running = _running()
    if running:
        prog['state'] = 'running'
    elif prog.get('state') == 'running':
        prog['state'] = 'error'
        prog['message'] = 'اسکریپت به‌طور غیرعادی بسته شد؛ reports/_last_run.log را ببینید.'
    prog['running'] = running
    prog['kind'] = _job['kind'] if running else prog.get('kind', '')
    tail = ''
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            tail = ''.join(f.readlines()[-6:])
    except Exception:
        pass
    prog['log_tail'] = tail
    return jsonify(prog)


@app.route('/retry_single', methods=['POST'])
def retry_single():
    url = (request.get_json(silent=True) or {}).get('url')
    if not url:
        return jsonify({'status': 'error'}), 400
    # اسکن سریع هم باید مثل اسکن اصلی claim شود؛ وگرنه دو درخواست هم‌زمان
    # می‌توانند هم‌زمان CSVها را بازنویسی کنند.
    with _job_lock:
        if _running():
            return _busy_response()
        _job['proc'] = 'sync'
        _job['tools'] = list(TOOLS)
        _job['kind'] = 'retry'
    try:
        r = subprocess.run([sys.executable, os.path.join(BASE_DIR, 'retry_single.py'), url], cwd=BASE_DIR,
                           env=_child_env(), capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=600)
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'message': 'اسکن سریع بیش از حد طول کشید.'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'خطا در اجرای اسکن سریع: {type(e).__name__}'}), 500
    finally:
        with _job_lock:
            _job['proc'] = None
            _job['tools'] = []
            _job['kind'] = ''
    if r.returncode == 0:
        return jsonify({'status': 'success'})
    if r.returncode == 2:
        return jsonify({'status': 'error', 'message': 'اینترنت/VPN وصل نیست؛ نتیجه قبلی دست نخورد.'}), 503
    return jsonify({'status': 'error', 'message': (r.stdout or r.stderr or '')[-400:]}), 500

# ---------------------------------------------------------------- آرشیو / حذف / نتایج
@app.route('/archive', methods=['POST'])
def archive_data():
    if _running():
        return _busy_response()
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    zip_name = os.path.join(ARCHIVE_DIR, f"qa_backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip")
    files = [os.path.join(REPORTS_DIR, i['output']) for i in TOOLS.values()]
    files = [f for f in files if os.path.exists(f)]
    if not files:
        return jsonify({'status': 'warning', 'message': 'اطلاعاتی برای آرشیو یافت نشد.'})
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, os.path.basename(f))
        if os.path.exists(URLS_FILE):
            z.write(URLS_FILE, 'urls.txt')
    for f in files:
        os.remove(f)
    if os.path.exists(qc.PROGRESS_FILE):
        os.remove(qc.PROGRESS_FILE)
    return jsonify({'status': 'success', 'message': 'اطلاعات امروز آرشیو و سیستم صفر شد.'})


@app.route('/delete/<tool_id>', methods=['POST'])
def delete_result(tool_id):
    if tool_id not in TOOLS:
        return jsonify({'status': 'error'}), 404
    if _running() and tool_id in _job['tools']:
        return _busy_response()
    p = os.path.join(REPORTS_DIR, TOOLS[tool_id]['output'])
    if os.path.exists(p):
        os.remove(p)
    return jsonify({'status': 'success'})


@app.route('/results/<tool_id>')
def get_results(tool_id):
    if tool_id not in TOOLS:
        return jsonify({'status': 'error'}), 404
    data, _ = get_tool_data(TOOLS[tool_id]['output'])
    for r in data:
        r['_level'] = qc.status_level(r.get('Status', ''))
    if not data:
        return jsonify({'status': 'empty', 'data': []})
    return jsonify({'status': 'success', 'data': data})


if __name__ == '__main__':
    # debug=False: در حالت debug سرور دوبار بالا می‌آید و اسکن‌ها ممکن است دوبار اجرا شوند
    app.run(debug=False, host='127.0.0.1', port=5000, threaded=True)
