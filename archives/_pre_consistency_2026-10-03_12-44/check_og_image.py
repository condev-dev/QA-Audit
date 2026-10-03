# -*- coding: utf-8 -*-
import sys
import time
import qa_core as qc

TOOL_ID = 'og_image'
CSV_NAME = 'og_image_report.csv'
FIELDS = ['URL', 'Image URL', 'Status']
MAX_TRY = 6

def _candidates(snap):
    out, seen = [], set()
    for u in (snap.get('og') or []):
        u = (u or '').strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def analyze(ctx, snap):
    gate = qc.content_gate(snap)
    cands = _candidates(snap)
    img = cands[0] if cands else '-'
    
    if gate:
        return {'Image URL': img, 'Status': gate}
        
    if not cands:
        return {'Image URL': '-', 'Status': 'خطا: صفحه تگ og:image ندارد'}

    referer = snap.get('final_url') or snap['url']
    deadline = time.time() + qc.ASSET_BUDGET_S
    results = []
    
    for u in cands[:MAX_TRY]:
        level, reason = qc.check_asset(ctx, u, referer)
        results.append((u, level, reason))
        
        if level == 'ok':
            return {'Image URL': u, 'Status': f'سالم ({reason})'}
            
        if time.time() > deadline:
            break

    u0, _, r0 = results[0]
    if all(lv == 'warn' for _, lv, _ in results):
        return {'Image URL': u0, 'Status': f'نیاز به بررسی دستی: {r0}'}
    return {'Image URL': u0, 'Status': f'خطا: تصویر OG — {r0}'}

if __name__ == '__main__':
    sys.exit(qc.run_checks([sys.modules[__name__]]))
