"""Read-only account/catalog checks; private versioned files, no inference calls."""
import json
import os
from pathlib import Path
import requests
from local_recall import MODULE, destination, write_json, pin

OUT = MODULE / 'evidence_closure_budget_preflight_v1'

def main():
    destination(OUT).mkdir(mode=0o700)
    report = {'paid_inference_requests': 0, 'checks': {}}
    def get(url, key_env=None):
        headers = {}
        if key_env:
            key = os.environ.get(key_env)
            if not key: return None, 'key_missing'
            headers['Authorization'] = 'Bearer ' + key
        try:
            r = requests.get(url, headers=headers, timeout=35, allow_redirects=False)
            if r.status_code != 200: return None, 'http_' + str(r.status_code)
            return r, 'ok'
        except requests.RequestException as e:
            return None, type(e).__name__
    r, status = get('https://api.deepseek.com/user/balance', 'DEEPSEEK_API_KEY')
    if r:
        p = r.json()
        report['checks']['deepseek_balance'] = {'status':status, 'is_available':p.get('is_available'),
            'balance_infos':[{k:b.get(k) for k in ('currency','total_balance','granted_balance','topped_up_balance')} for b in p.get('balance_infos',[])]}
    else: report['checks']['deepseek_balance'] = {'status':status}
    r, status = get('https://openrouter.ai/api/v1/key', 'OPENROUTER_API_KEY')
    report['checks']['openrouter_key'] = {'status':status}
    if r:
        d = r.json().get('data',{})
        report['checks']['openrouter_key'].update({k:d.get(k) for k in ('usage','usage_daily','limit','limit_remaining','is_free_tier','include_byok_in_limit')})
    r, status = get('https://openrouter.ai/api/v1/models')
    matches = [d for d in r.json().get('data',[]) if d.get('id')=='openai/gpt-5.6-luna'] if r else []
    report['checks']['openrouter_catalog'] = {'status':status, 'matches':[{k:d.get(k) for k in ('id','name','pricing','context_length','top_provider')} for d in matches]}
    pages = {
      'deepseek_pricing_cn.html':'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
      'zhipu_pricing.md':'https://docs.bigmodel.cn/cn/guide/start/pricing.md',
      'zhipu_pricing.html':'https://open.bigmodel.cn/pricing',
      'openai_luna.md':'https://developers.openai.com/api/docs/models/gpt-5.6-luna.md'}
    for name,url in pages.items():
        r, status = get(url)
        info = {'url':url, 'status':status}
        if r:
            p=OUT/name; p.write_bytes(r.content); p.chmod(0o600); info.update(pin(p))
        report['checks'][name] = info
    write_json(OUT/'summary.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
