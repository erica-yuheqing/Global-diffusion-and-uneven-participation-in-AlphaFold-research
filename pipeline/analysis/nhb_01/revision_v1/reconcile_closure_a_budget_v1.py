"""Read actual account debit only after A has no in-flight stage requests."""
from decimal import Decimal
import json
import os
import requests
from closure_execution_v3 import Ledger, OUT as EXECUTION, PREFLIGHT
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, pin, require, write_json

OUT = MODULE / 'evidence_closure_a_budget_reconciliation_v1'


def cny_balance(value):
    rows = [r for r in value.get('balance_infos', []) if r.get('currency') == 'CNY']
    require(len(rows) == 1, 'Expected one CNY balance')
    row = rows[0]
    total = Decimal(str(row['total_balance']))
    granted = Decimal(str(row['granted_balance']))
    require(total.is_finite() and total >= 0 and granted == 0, 'Balance/grant reconciliation unavailable')
    return total


def main():
    manifests = list((EXECUTION / 'model_a_closure_v3.artifacts').glob('*/run_manifest.json'))
    require(manifests and all(json.loads(p.read_text()).get('status') in
        ('completed', 'completed_with_failures') for p in manifests), 'A is not fully stopped/archived')
    ledger = Ledger()
    with ledger.locked():
        rows = ledger.rows(); starts, finishes, totals = ledger.accounting(rows)
        numbers = sorted(n for n, row in starts.items() if row['model_key'] == 'a')
        require(all(n in finishes for n in numbers), 'A still has unsettled HTTP sends')
    baseline = json.loads(PREFLIGHT.read_text())['checks']['deepseek_balance']
    before = cny_balance(baseline)
    key = os.environ.get('DEEPSEEK_API_KEY')
    require(bool(key), 'DeepSeek key missing')
    response = requests.get('https://api.deepseek.com/user/balance',
        headers={'Authorization': 'Bearer ' + key}, timeout=35, allow_redirects=False)
    require(response.status_code == 200, 'Balance request failed; do not relax reservation')
    raw = response.json()
    current = {'is_available': raw.get('is_available'),
        'balance_infos': [{k: r.get(k) for k in
            ('currency', 'total_balance', 'granted_balance', 'topped_up_balance')}
            for r in raw.get('balance_infos', [])]}
    after = cny_balance(current); debit = before - after
    require(Decimal(0) <= debit <= totals['a'], 'Balance delta inconsistent; retain original guard')
    require(debit <= Decimal('19'), 'Authorized actual A expenditure exhausted')
    out = destination(OUT); out.mkdir(mode=0o700)
    write_json(out / 'filtered_current_balance.json', current)
    record = {'schema': 'actual-account-debit-reconciliation-v1',
        'model': 'a', 'currency': 'CNY', 'request_numbers': numbers,
        'starting_balance': str(before), 'current_balance': str(after),
        'actual_account_debit_conservative_of_all_account_use': str(debit),
        'old_peak_no_cache_accounting_ceiling': str(totals['a']),
        'authorized_maximum_new_spend': '19', 'new_provider_requests': 0,
        'limitation': 'Balance delta includes any other simultaneous account spending; no recharge/grant accepted. Historical token ceilings and all request records remain unchanged.'}
    write_json(out / 'reconciliation.json', record)
    write_json(out / 'run_manifest.json', {'schema': 'closure-account-reconciliation-archive-v1',
        'inputs': [pin(PREFLIGHT), pin(EXECUTION / 'paid_request_ledger.jsonl'), pin(__file__)],
        'summary': record, 'outputs': inventory(out)})
    print('Actual A account debit:', str(debit), 'CNY; historical conservative ceiling:', str(totals['a']),
          '; authorization still 19 CNY; old settlements unchanged', flush=True)


if __name__ == '__main__':
    main()
