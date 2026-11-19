"""Complete never-dispatched A records after independently archived balance debit."""
from decimal import Decimal
import json
from pathlib import Path
import closure_execution_v3 as original
from closure_execution_v3_1 import GuardedLedger
from fetch_public_evidence import inventory
from local_recall import MODULE, pin, require, write_json
from reconcile_closure_a_budget_v1 import OUT as RECONCILIATION

REFERENCE = RECONCILIATION / 'reconciliation.json'
MANIFEST = RECONCILIATION / 'run_manifest.json'
BASE_ACCOUNTING = original.Ledger.accounting
BASE_READ = original.read_jsonl


def reconcile_accounting(rows, reference):
    starts, finishes, totals = BASE_ACCOUNTING(rows)
    numbers = set(reference['request_numbers'])
    require(numbers and all(n in starts and n in finishes and starts[n]['model_key'] == 'a'
        for n in numbers), 'Reconciliation request set differs')
    old_ceiling = sum((Decimal(finishes[n]['accounted_cost']) for n in numbers), Decimal(0))
    require(old_ceiling == Decimal(reference['old_peak_no_cache_accounting_ceiling']),
        'Historical A cost records changed')
    actual = Decimal(reference['actual_account_debit_conservative_of_all_account_use'])
    require(Decimal(0) <= actual <= old_ceiling, 'Reconciliation does not bound actual debit')
    totals['a'] = totals['a'] - old_ceiling + actual
    return starts, finishes, totals


class ReconciledLedger(GuardedLedger):
    @staticmethod
    def accounting(rows):
        manifest = json.loads(MANIFEST.read_text())
        require(inventory(RECONCILIATION) == manifest['outputs'], 'Balance archive changed')
        return reconcile_accounting(rows, json.loads(REFERENCE.read_text()))


def main():
    manifests = list((original.OUT / 'model_a_closure_v3.artifacts').glob('*/run_manifest.json'))
    require(manifests and all(json.loads(p.read_text()).get('status') in
        ('completed', 'completed_with_failures') for p in manifests), 'Another A writer is active')
    record = json.loads(REFERENCE.read_text())
    require(Decimal(record['actual_account_debit_conservative_of_all_account_use']) <= Decimal('19'),
        'No authorized A funds remain')
    starts = [r for r in BASE_READ(original.OUT / 'paid_request_ledger.jsonl')
              if r.get('event') == 'reserved_dispatch' and r.get('model_key') == 'a']
    dispatched = {r['work_id'] for r in starts}
    audit = original.OUT / 'model_a_closure_v3.attempts.jsonl'

    def actual_attempts(path):
        rows = BASE_READ(path)
        if Path(path) == audit:
            # A request_started event precedes the monetary guard in the legacy
            # runner. Guard-denied events are not paid attempts, hence may now be
            # dispatched; successful/invalid actual HTTP sends are never retried.
            rows = [r for r in rows if r.get('event') != 'request_started' or r['work_id'] in dispatched]
        return rows

    write_json(MODULE / 'evidence_closure_a_reconciled_execution_v1.json', {
        'schema': 'closure-A-actual-debit-guard-continuation-v1',
        'pins': [pin(__file__), pin(REFERENCE), pin(MANIFEST)],
        'retry_actual_HTTP_attempts': False, 'old_prompt_schema_settings_unchanged': True,
        'budget_CNY': '19', 'aggregate_paid_request_cap': 5274})
    original.Ledger = ReconciledLedger; original.read_jsonl = actual_attempts
    original.run_model('a', MODULE / 'evidence_closure_api_inputs_v3/closure586_model_inputs.jsonl')


if __name__ == '__main__':
    main()
