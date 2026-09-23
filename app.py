from flask import Flask, render_template, jsonify
import subprocess
import os
import csv

app = Flask(__name__)

TOOLS = {
    'title': {'script': 'check_title.py', 'output': 'title_report.csv', 'type': 'csv'},
    'description': {'script': 'check_description.py', 'output': 'description_report.csv', 'type': 'csv'},
    'og_image': {'script': 'check_og_image.py', 'output': 'og_image_report.csv', 'type': 'csv'},
    'source_encoding': {'script': 'check_source_encoding.py', 'output': 'source_encoding_report.csv', 'type': 'csv'},
    'favicon': {'script': 'check_favicon.py', 'output': 'favicon_report.csv', 'type': 'csv'}
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/urls')
def get_base_urls():
    if not os.path.exists('urls.txt'):
        return jsonify([])
        
    with open('urls.txt', 'r', encoding='utf-8-sig') as f:
        raw_urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
    reports = {'title': {}, 'description': {}, 'og_image': {}, 'source_encoding': {}, 'favicon': {}}
    for tool_id, tool_info in TOOLS.items():
        file_name = tool_info['output']
        if os.path.exists(file_name):
            with open(file_name, 'r', encoding='utf-8-sig') as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    reports[tool_id][row['URL']] = row
                    
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
        try:
            subprocess.run(['python', script_name], check=True)
            return jsonify({"status": "success", "message": f"{script_name} با موفقیت اجرا شد."})
        except subprocess.CalledProcessError:
            return jsonify({"status": "error", "message": "خطا در اجرای اسکریپت."}), 500
    return jsonify({"status": "error", "message": "ابزار یافت نشد."}), 404

@app.route('/delete/<tool_id>', methods=['POST'])
def delete_result(tool_id):
    if tool_id in TOOLS:
        file_name = TOOLS[tool_id]['output']
        if os.path.exists(file_name):
            os.remove(file_name)
            return jsonify({"status": "success", "message": "گزارش با موفقیت پاک شد."})
        return jsonify({"status": "warning", "message": "هیچ گزارشی برای پاک کردن وجود ندارد."})
    return jsonify({"status": "error", "message": "ابزار یافت نشد."}), 404

@app.route('/results/<tool_id>')
def get_results(tool_id):
    if tool_id not in TOOLS:
        return jsonify({"status": "error", "message": "ابزار یافت نشد."}), 404
        
    file_name = TOOLS[tool_id]['output']
    
    if not os.path.exists(file_name):
        return jsonify({"status": "empty", "data": []})
        
    data = []
    with open(file_name, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        data = list(reader)
            
    return jsonify({"status": "success", "data": data})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
