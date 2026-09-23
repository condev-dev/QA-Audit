from flask import Flask, render_template, jsonify, request
import subprocess
import os
import csv
import zipfile
import shutil
from datetime import datetime

app = Flask(__name__)

REPORTS_DIR = 'reports'
if not os.path.exists(REPORTS_DIR):
    os.makedirs(REPORTS_DIR)

TOOLS = {
    'title': {'script': 'check_title.py', 'output': 'title_report.csv'},
    'description': {'script': 'check_description.py', 'output': 'description_report.csv'},
    'og_image': {'script': 'check_og_image.py', 'output': 'og_image_report.csv'},
    'source_encoding': {'script': 'check_source_encoding.py', 'output': 'source_encoding_report.csv'},
    'favicon': {'script': 'check_favicon.py', 'output': 'favicon_report.csv'}
}

def get_tool_data(output_filename):
    data_dict = {}
    rep_path = os.path.join(REPORTS_DIR, output_filename)
    
    # اول از فایل نهایی در پوشه گزارش‌ها می‌خواند (اگر قبلاً اسکن تمام شده باشد)
    if os.path.exists(rep_path):
        with open(rep_path, 'r', encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                data_dict[row['URL']] = row
                
    # سپس از فایلی که همین الان در حال نوشته شدن است می‌خواند
    # (این همان جادویی است که ویژگی نمایش زنده و Real-Time شما را برمی‌گرداند)
    if os.path.exists(output_filename):
        try:
            with open(output_filename, 'r', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    data_dict[row['URL']] = row
        except:
            pass
            
    return list(data_dict.values()), data_dict

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/urls')
def get_base_urls():
    if not os.path.exists('urls.txt'):
        return jsonify([])
        
    with open('urls.txt', 'r', encoding='utf-8-sig') as f:
        raw_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
    reports = {}
    for tool_id, tool_info in TOOLS.items():
        _, data_dict = get_tool_data(tool_info['output'])
        reports[tool_id] = data_dict
            
    results = []
    for url in raw_urls:
        formatted = url if url.startswith('http') else 'https://' + url
        
        t_row = reports['title'].get(formatted, {})
        d_row = reports['description'].get(formatted, {})
        o_row = reports['og_image'].get(formatted, {})
        s_row = reports['source_encoding'].get(formatted, {})
        f_row = reports['favicon'].get(formatted, {})

        errors = []
        if 'خطا' in t_row.get('Status', '') or 'نیاز' in t_row.get('Status', ''): errors.append('تایتل')
        if 'خطا' in d_row.get('Status', '') or 'نیاز' in d_row.get('Status', ''): errors.append('دیسکریپشن')
        if 'خطا' in o_row.get('Status', '') or 'نیاز' in o_row.get('Status', ''): errors.append('عکس OG')
        if 'خطا' in s_row.get('Status', '') or 'نیاز' in s_row.get('Status', ''): errors.append('سورس')
        if 'خطا' in f_row.get('Status', '') or 'نیاز' in f_row.get('Status', ''): errors.append('فوآیکون')
        
        results.append({
            "raw_url": url,
            "formatted_url": formatted,
            "errors": errors,
            "details": {
                "title": {"status": t_row.get('Status', 'بررسی نشده'), "text": t_row.get('Title Text', '-')},
                "description": {"status": d_row.get('Status', 'بررسی نشده'), "text": d_row.get('Description Text', '-')},
                "og_image": {"status": o_row.get('Status', 'بررسی نشده'), "text": o_row.get('Image URL', '-')},
                "source_encoding": {"status": s_row.get('Status', 'بررسی نشده')},
                "favicon": {"status": f_row.get('Status', 'بررسی نشده'), "text": f_row.get('Favicon URL', '-')}
            }
        })
        
    return jsonify(results)

@app.route('/run/<tool_id>', methods=['POST'])
def run_tool(tool_id):
    if tool_id in TOOLS:
        script_name = TOOLS[tool_id]['script']
        output_file = TOOLS[tool_id]['output']
        
        # قبل از استارت، دیتاهای قدیمی پاک می‌شوند تا اسکن از صفر شروع شود
        if os.path.exists(output_file): os.remove(output_file)
        rep_path = os.path.join(REPORTS_DIR, output_file)
        if os.path.exists(rep_path): os.remove(rep_path)
        
        try:
            subprocess.run(['python', script_name], check=True)
            
            # پس از اتمام کامل، فایل برای تمیز ماندن محیط به پوشه گزارش‌ها می‌رود
            if os.path.exists(output_file):
                shutil.move(output_file, rep_path)
                
            return jsonify({"status": "success"})
        except subprocess.CalledProcessError:
            return jsonify({"status": "error"}), 500
    return jsonify({"status": "error"}), 404

@app.route('/retry_single', methods=['POST'])
def retry_single():
    url = request.json.get('url')
    if not url: return jsonify({"status": "error"}), 400
    try:
        subprocess.run(['python', 'retry_single.py', url], check=True)
        return jsonify({"status": "success"})
    except subprocess.CalledProcessError:
        return jsonify({"status": "error"}), 500

@app.route('/archive', methods=['POST'])
def archive_data():
    if not os.path.exists('archives'): os.makedirs('archives')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_name = f"archives/qa_backup_{date_str}.zip"
    
    files_to_zip = [os.path.join(REPORTS_DIR, info['output']) for info in TOOLS.values()]
    archived_any = False
    
    with zipfile.ZipFile(zip_name, 'w') as zipf:
        for file_path in files_to_zip:
            if os.path.exists(file_path):
                zipf.write(file_path, os.path.basename(file_path))
                archived_any = True
                
    if archived_any:
        for file_path in files_to_zip:
            if os.path.exists(file_path): os.remove(file_path)
        return jsonify({"status": "success", "message": "اطلاعات امروز با موفقیت آرشیو شد."})
    else:
        if os.path.exists(zip_name): os.remove(zip_name)
        return jsonify({"status": "warning", "message": "گزارشی برای آرشیو یافت نشد."})

@app.route('/delete/<tool_id>', methods=['POST'])
def delete_result(tool_id):
    if tool_id in TOOLS:
        output_file = TOOLS[tool_id]['output']
        if os.path.exists(output_file): os.remove(output_file)
        rep_path = os.path.join(REPORTS_DIR, output_file)
        if os.path.exists(rep_path): os.remove(rep_path)
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 404

@app.route('/results/<tool_id>')
def get_results(tool_id):
    if tool_id not in TOOLS: return jsonify({"status": "error"}), 404
    
    data_list, _ = get_tool_data(TOOLS[tool_id]['output'])
    if not data_list:
        return jsonify({"status": "empty", "data": []})
        
    return jsonify({"status": "success", "data": data_list})

if __name__ == '__main__':
    # threaded=True امکان اجرای همزمان ربات‌ها را به سرور می‌دهد
    app.run(debug=True, port=5000, threaded=True)
