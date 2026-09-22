from flask import Flask, render_template, jsonify
import subprocess
import os
import csv

app = Flask(__name__)

TOOLS = {
    'title': {'script': 'check_title.py', 'output': 'title_report.csv', 'type': 'csv'},
    'description': {'script': 'check_description.py', 'output': 'description_report.csv', 'type': 'csv'},
    'og_image': {'script': 'check_og_image.py', 'output': 'og_image_report.csv', 'type': 'csv'},
    'source_encoding': {'script': 'check_source_encoding.py', 'output': 'source_encoding_report.csv', 'type': 'csv'}
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
        
    # خواندن وضعیت آخرین گزارش‌ها از فایل‌های CSV
    reports = {'title': {}, 'description': {}, 'og_image': {}, 'source_encoding': {}}
    for tool_id, tool_info in TOOLS.items():
        file_name = tool_info['output']
        if os.path.exists(file_name):
            with open(file_name, 'r', encoding='utf-8-sig') as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    # ذخیره وضعیت هر لینک در دیکشنری
                    reports[tool_id][row['URL']] = row.get('Status', '')
                    
    results = []
    for url in raw_urls:
        formatted = url if url.startswith('http') else 'https://' + url
        errors = []
        
        # بررسی وجود خطا در هر یک از ۴ گزارش
        if 'خطا' in reports['title'].get(formatted, '') or 'نیاز' in reports['title'].get(formatted, ''): errors.append('تایتل')
        if 'خطا' in reports['description'].get(formatted, '') or 'نیاز' in reports['description'].get(formatted, ''): errors.append('دیسکریپشن')
        if 'خطا' in reports['og_image'].get(formatted, '') or 'نیاز' in reports['og_image'].get(formatted, ''): errors.append('عکس OG')
        if 'خطا' in reports['source_encoding'].get(formatted, '') or 'نیاز' in reports['source_encoding'].get(formatted, ''): errors.append('سورس')
        
        results.append({
            "raw_url": url,
            "formatted_url": formatted,
            "errors": errors
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
