"""Final filtered account/ledger reconciliation; no inference or source edits."""
from collections import Counter
from decimal import Decimal
import json
import os
import requests
from closure_execution_v3 import Ledger, OUT as EXECUTION, PREFLIGHT
from reconcile_closure_a_budget_v1 import cny_balance
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, pin, require, write_json

OUT = MODULE / 'evidence_closure_final_budget_v1'


def get_filtered(url, variable, fields, nested=None):
    key = os.environ.get(variable)
    if not key:
        return {'status': 'key_missing'}
    try:
        response = requests.get(url, headers={'Authorization': 'Bearer ' + key},
                                timeout=35, allow_redirects=False)
        if response.status_code != 200:
            return {'status': 'http_' + str(response.status_code)}
        value = response.json()
        if nested:
            value = value.get(nested, {})
        return {'status': 'ok', **{k: value.get(k) for k in fields}}
    except (requests.RequestException, ValueError):
        return {'status': 'unavailable_no_zero_imputation'}


def summarize(rows, preflight, deepseek, openrouter):
    starts, finishes, ceilings = Ledger.accounting(rows)
    require(starts and set(starts) == set(finishes), 'Unsettled HTTP sends remain')
    require(len(starts) <= 5274, 'Aggregate paid HTTP send cap exceeded')
    result = {'actual_paid_HTTP_sends': len(starts), 'aggregate_cap': 5274,
              'by_model_sends': dict(Counter(r['model_key'] for r in starts.values())),
              'historical_token_ceiling_not_bill': {k: str(v) for k, v in ceilings.items()},
              'authorization_limits': {'a_CNY': '19', 'b_CNY': '39', 'c_USD': '9'},
              'account_checks': {}, 'new_inference_requests': 0,
              'old_ledger_changed': False}
    if deepseek.get('status') == 'ok':
        before = cny_balance(preflight['checks']['deepseek_balance'])
        after = cny_balance(deepseek)
        debit = before - after
        require(Decimal(0) <= debit <= Decimal('19'), 'A balance delta needs review')
        result['account_checks']['a'] = {
            'basis': 'official_CNY_balance_delta_all_account_activity',
            'starting_balance': str(before), 'ending_balance': str(after),
            'debit_CNY': str(debit), 'within_authorized_cap': True,
            'caveat': 'Includes concurrent account spending; recharge/refund invalidates attribution. Grants are not accepted.'}
    else:
        result['account_checks']['a'] = {'basis': 'unavailable_actual_bill_not_zero'}
    require(ceilings['b'] <= Decimal('39'), 'B conservative budget ceiling exceeded')
    require(ceilings['c'] <= Decimal('9'), 'C reported/reserved budget exceeded')
    result['account_checks']['b'] = {
        'basis': 'conservative_peak_no_cache_token_ceiling_plus_10_percent_not_actual_bill',
        'ceiling_CNY': str(ceilings['b']), 'within_authorized_cap': True}
    cs = [r for r in finishes.values() if r['model_key'] == 'c']
    known = [r for r in cs if r['basis'] == 'provider_reported_usd']
    result['account_checks']['c'] = {
        'reported_USD': str(sum((Decimal(r['accounted_cost']) for r in known), Decimal(0))),
        'attempts_with_reported_cost': len(known), 'actual_attempts': len(cs),
        'cost_reporting_complete': len(known) == len(cs),
        'reported_plus_unreported_reservation_USD': str(ceilings['c']),
        'unreported_cost': 'unknown_not_zero', 'within_authorized_cap': True}
    baseline = preflight['checks']['openrouter_key'].get('usage')
    current = openrouter.get('usage')
    if baseline is not None and current is not None:
        delta = Decimal(str(current)) - Decimal(str(baseline))
        result['account_checks']['c']['official_key_usage_delta_USD'] = str(delta)
        result['account_checks']['c']['usage_delta_caveat'] = 'Account/key-wide observation; includes concurrent use and reporting lag, not request attribution.'
    return result


def main():
    ledger = Ledger()
    with ledger.locked():
        rows = ledger.rows()
        starts, finishes, _ = ledger.accounting(rows)
        require(starts and set(starts) == set(finishes), 'Run still active; do not freeze billing')
    for model in ('a', 'b', 'c'):
        paths = list((EXECUTION / f'model_{model}_closure_v3.artifacts').glob('*/run_manifest.json'))
        require(paths and all(json.loads(p.read_text())['status'] in
            ('completed', 'completed_with_failures') for p in paths), 'Model archives not final: ' + model)
    ds = get_filtered('https://api.deepseek.com/user/balance', 'DEEPSEEK_API_KEY',
                      ('is_available', 'balance_infos'))
    if ds.get('status') == 'ok':
        ds['balance_infos'] = [{k: row.get(k) for k in
            ('currency', 'total_balance', 'granted_balance', 'topped_up_balance')}
            for row in ds.get('balance_infos') or []]
    router = get_filtered('https://openrouter.ai/api/v1/key', 'OPENROUTER_API_KEY',
                          ('usage', 'usage_daily', 'limit_remaining'), 'data')
    summary = summarize(rows, json.loads(PREFLIGHT.read_text()), ds, router)
    out = destination(OUT); out.mkdir(mode=0o700)
    write_json(out / 'filtered_account_checks.json', {'deepseek': ds, 'openrouter': router})
    write_json(out / 'summary.json', summary)
    write_json(out / 'run_manifest.json', {'schema': 'closure-final-budget-audit-v1',
        'inputs': [pin(PREFLIGHT), pin(ledger.path), pin(__file__)],
        'summary': summary, 'outputs': inventory(out)})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
