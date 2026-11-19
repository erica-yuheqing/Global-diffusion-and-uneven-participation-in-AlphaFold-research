"""Read-only export reconstruction and denominator checks; never publishes reports."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path
from common import MODULE, assert_unchanged, connect, literal, output_dir, read_json
from baseline_features import fingerprint
from activity_patterns import (CODE, CONFIG, GUIDE, EXPORTS, FLOATS, KEYS, attach_sources, build_tables,
    check_tables, load_inputs, local_file, markdown, summary)
from validate_leadership_rr import numeric_difference


def verify(directory, threads=2, memory_gib=4):
    import pyarrow.parquet as pq
    directory = output_dir(Path(directory), existing=True)
    m = read_json(local_file(directory / 'activity_manifest.json'))
    if (m.get('schema_version') != 'nhb-activity-patterns-run-v1' or m.get('provider_requests') != 0 or
        m.get('original_final_database_modified') is not False or m.get('formal_models_ready') is not False or
        m.get('independent_human_gold_standard') is not False or m.get('complete_version_deduplication_claimed') is not False):
        raise ValueError('Artifact scope/authority differs')
    c, inv, dirs = load_inputs({k: Path(v) for k, v in m['directories'].items()})
    if (m['config'] != c or [(r['path'], r['sha256']) for r in m['inputs']] !=
        [(r['path'], r['sha256']) for r in inv]):
        raise ValueError('Source / policy / code differs from this artifact')
    expected_outputs = {n + '.parquet' for n in EXPORTS} | {
        'activity_summary.json', 'activity_report_zh.md', 'validation_report.json'}
    if set(m['outputs']) != expected_outputs:
        raise ValueError('Export inventory differs')
    if set(m['snapshots']) != {'code_and_policy/' + n for n in CODE + (CONFIG.name, GUIDE.name)}:
        raise ValueError('Code / policy snapshot inventory differs')
    for rel, expected in {**m['outputs'], **m['snapshots']}.items():
        p = local_file(directory / rel)
        if not p.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Unsafe export/snapshot path')
        fp = fingerprint(p)
        if fp['sha256'] != expected['sha256'] or fp['size_bytes'] != expected['size_bytes']:
            raise ValueError('Export/snapshot changed: ' + rel)
        if p.suffix == '.parquet':
            pf = pq.ParquetFile(p)
            if pf.metadata.num_rows != expected['rows'] or expected['rows'] > c['maximum_export_rows']:
                raise ValueError('Export row metadata differs')
    con = connect(threads, memory_gib)
    try:
        attach_sources(con, dirs)
        build_tables(con, dirs, c)
        checks = check_tables(con)
        # Shared reconstruction is not independent semantic adjudication. Float comparisons
        # use the existing scale-aware tolerance, NULL equality and exact nonnumeric fields.
        for name in EXPORTS:
            saved = 'saved_' + name
            con.execute(f'CREATE VIEW {saved} AS SELECT * FROM read_parquet({literal(directory/(name+".parquet"))})')
            checks[name + '_export_reconstruction'] = numeric_difference(
                con, saved, name, KEYS[name], FLOATS.get(name, []))
            keys = ','.join(KEYS[name])
            checks[name + '_saved_duplicate_keys'] = int(con.execute(
                f'SELECT count(*) FROM (SELECT {keys},count(*) AS n FROM {saved} GROUP BY ALL HAVING n<>1)').fetchone()[0])
        s = summary(con)
        checks['summary_reconstruction'] = int(s != read_json(directory / 'activity_summary.json'))
        checks['markdown_reconstruction'] = int(markdown(s) != (directory / 'activity_report_zh.md').read_text(encoding='utf-8'))
        report = read_json(directory / 'validation_report.json')
        base_checks = {k: v for k, v in checks.items() if not k.endswith(('_export_reconstruction', '_saved_duplicate_keys'))
                       and k not in ('summary_reconstruction', 'markdown_reconstruction')}
        checks['saved_report_scope'] = int(report != {
            'schema_version': 'nhb-activity-patterns-validation-v1', 'checks': base_checks,
            'blockers': [], 'activity_descriptives_ready': True, 'descriptive_activity_rr_ready': True,
            'formal_models_ready': False, 'independent_human_gold_standard': False,
            'export_reconstruction_required': True})
        checks['manifest_checks'] = int(m['checks'] != base_checks)
        assert_unchanged(inv)
        if any(checks.values()):
            raise ValueError('Activity reconstruction blockers: ' + str({k: v for k, v in checks.items() if v}))
        return {'checks': len(checks), 'blockers': 0, 'confirmed_AF_main_studies': s['confirmed_AF_main_studies'],
                'activity_descriptives_ready': True, 'descriptive_activity_rr_ready': True,
                'formal_models_ready': False, 'provider_requests': 0}
    finally:
        con.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', type=Path, default=MODULE / 'activity_patterns_v1')
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--memory-gib', type=int, default=4)
    args = p.parse_args(argv)
    if not 1 <= args.threads <= 16 or not 1 <= args.memory_gib <= 32:
        p.error('threads 1..16; memory-gib 1..32')
    result = verify(args.input_dir, args.threads, args.memory_gib)
    print('Activity export reconstruction: PASS; checks: ' + str(result['checks']) + '; blockers: 0')
    print('Confirmed AF main studies: ' + str(result['confirmed_AF_main_studies']))
    print('Activity descriptives / descriptive activity RR ready: True; formal models ready: False')
    print('No API, writes, core/final changes or independent semantic certification')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
